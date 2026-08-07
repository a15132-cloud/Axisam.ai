"""Capa 2 - the orchestrator agent loop.

Standard Anthropic tool-use loop: send the conversation + tool defs, run
whatever tools Claude calls, feed results back, repeat until it stops
calling tools or we hit the iteration cap. The one non-standard piece is
`_resumen_estado`: the real project state (from the database of record,
not from what the model said earlier in the chat) is appended to every
user turn, because the system prompt's safety rules are only as good as
the ground truth backing them - see app/agent/approval.py for why the
actual checkpoint transitions never happen from in here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import anthropic

from app.config import settings
from app.schemas.project import Proyecto
from app.tools import definitions, handlers

MAX_ITERACIONES_HERRAMIENTAS = 6

SYSTEM_PROMPT = """Eres Axiscam, el agente que orquesta el flujo de diseno y manufactura de un taller:
lectura de planos -> modelo 3D -> trayectorias de maquinado -> codigo G, con SolidWorks y Mastercam
trabajando en segundo plano. Hablas en espanol con el usuario del taller, directo y concreto.

REGLAS DE SEGURIDAD QUE NUNCA ROMPES:
1. Los tres checkpoints humanos (confirmar extraccion, confirmar modelo 3D, aprobacion final antes de
   codigo G) SOLO ocurren por una accion explicita del usuario en la interfaz (un boton), nunca porque
   tu lo decidas o porque el usuario lo mencione de pasada en el chat. El "Estado actual del proyecto"
   que recibes en cada mensaje es la unica fuente de verdad - si el usuario dice "ya confirme" pero el
   estado no lo refleja, dile que use el boton de confirmacion correspondiente; no llames ninguna
   herramienta basandote solo en su mensaje.
2. Nunca digas que un codigo G esta listo para cargarse en la maquina sin recordar que sigue pendiente
   de verificacion con Mastercam real y de revision de un maquinista - incluso despues de la aprobacion
   final en el sistema.
3. Si una herramienta falla por precondicion no cumplida, explica exactamente que boton o accion falta
   en la interfaz - no reintentes la misma llamada.
4. Los valores de corte (velocidades, avances, herramientas) vienen de una base de reglas de referencia
   sin validar todavia por un maquinista humano - menciona esto la primera vez que compartas parametros
   de corte en la conversacion.
5. Si el usuario pide algo fuera de lo que las herramientas disponibles pueden hacer (p.ej. un tipo de
   maquinado no soportado aun), dilo claramente en vez de improvisar una respuesta que suene segura."""


@dataclass
class ResultadoTurno:
    texto_respuesta: str
    herramientas_ejecutadas: list[str]


def _resumen_estado(proyecto: Proyecto) -> str:
    resumen = {
        "etapa": proyecto.etapa.value,
        "pieza_confirmada": proyecto.pieza_confirmada,
        "modelo_confirmado": proyecto.modelo_confirmado,
        "aprobacion_final": proyecto.aprobacion_final,
        "tiene_pieza_extraida": proyecto.pieza_extraida is not None,
        "tiene_plan_trayectorias": proyecto.toolpath_plan is not None,
        "tiene_simulacion": proyecto.simulacion is not None,
        "archivos_generados": [a.nombre for a in proyecto.archivos],
    }
    return json.dumps(resumen, ensure_ascii=False)


_DISPATCH = {
    "generar_modelo_3d": lambda proyecto, args: handlers.generar_modelo_3d(proyecto),
    "generar_trayectorias": lambda proyecto, args: handlers.generar_trayectorias(proyecto, args.get("postprocesador")),
    "simular_maquinado": lambda proyecto, args: handlers.simular_maquinado(proyecto),
    "exportar_codigo_g": lambda proyecto, args: handlers.exportar_codigo_g(proyecto),
}


def ejecutar_turno(
    proyecto: Proyecto,
    mensaje_usuario: str,
    client: anthropic.Anthropic | None = None,
) -> ResultadoTurno:
    if not settings.anthropic_api_key and client is None:
        raise RuntimeError("ANTHROPIC_API_KEY no esta configurada en el servidor.")

    active_client = client or anthropic.Anthropic(api_key=settings.anthropic_api_key)
    mensajes: list[dict] = list(proyecto.mensajes)
    mensajes.append(
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": f"{mensaje_usuario}\n\n[Estado actual del proyecto: {_resumen_estado(proyecto)}]",
                }
            ],
        }
    )

    herramientas_ejecutadas: list[str] = []
    texto_final = ""

    for _ in range(MAX_ITERACIONES_HERRAMIENTAS):
        response = active_client.messages.create(
            model=settings.claude_model_agent,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=definitions.TODAS,
            messages=mensajes,
        )

        bloques_asistente = [b.model_dump() for b in response.content]
        mensajes.append({"role": "assistant", "content": bloques_asistente})
        texto_final = "\n".join(b["text"] for b in bloques_asistente if b["type"] == "text")

        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if not tool_uses:
            break

        resultados_tool: list[dict] = []
        for tool_use in tool_uses:
            handler = _DISPATCH.get(tool_use.name)
            if handler is None:
                resultados_tool.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": f"Herramienta desconocida: {tool_use.name}",
                        "is_error": True,
                    }
                )
                continue
            try:
                resultado = handler(proyecto, tool_use.input or {})
                herramientas_ejecutadas.append(tool_use.name)
                resultados_tool.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use.id,
                        "content": json.dumps(resultado, ensure_ascii=False, default=str),
                    }
                )
            except handlers.PrecondicionNoCumplida as exc:
                resultados_tool.append(
                    {"type": "tool_result", "tool_use_id": tool_use.id, "content": str(exc), "is_error": True}
                )
            except Exception as exc:  # geometry/CAM errors go back to the model, never swallowed silently
                resultados_tool.append(
                    {"type": "tool_result", "tool_use_id": tool_use.id, "content": f"Error inesperado: {exc}", "is_error": True}
                )

        mensajes.append({"role": "user", "content": resultados_tool})

    proyecto.mensajes = mensajes
    return ResultadoTurno(texto_respuesta=texto_final, herramientas_ejecutadas=herramientas_ejecutadas)
