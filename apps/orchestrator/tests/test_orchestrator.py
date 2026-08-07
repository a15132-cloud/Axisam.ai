from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from app.agent import approval
from app.agent.orchestrator import MAX_ITERACIONES_HERRAMIENTAS, ejecutar_turno
from app.schemas.piece import Dimensiones, Feature, FormaBase, Material, Pieza, Posicion2D, TipoFeature
from app.schemas.project import Etapa, Proyecto
from app.tools import handlers


@dataclass
class _TextBlock:
    text: str
    type: str = "text"

    def model_dump(self):
        return {"type": "text", "text": self.text}


@dataclass
class _ToolUseBlock:
    id: str
    name: str
    input: dict
    type: str = "tool_use"

    def model_dump(self):
        return {"type": "tool_use", "id": self.id, "name": self.name, "input": self.input}


class _ScriptedClient:
    """Returns each response in `respuestas` in order, one per messages.create() call."""

    def __init__(self, respuestas: list[SimpleNamespace]):
        self._respuestas = list(respuestas)
        self.llamadas: list[dict] = []
        self.messages = self

    def create(self, **kwargs):
        self.llamadas.append(kwargs)
        return self._respuestas.pop(0)


def _respuesta_texto(texto: str, stop_reason: str = "end_turn") -> SimpleNamespace:
    return SimpleNamespace(content=[_TextBlock(texto)], stop_reason=stop_reason)


def _respuesta_tool_use(tool_id: str, name: str, tool_input: dict, stop_reason: str = "tool_use") -> SimpleNamespace:
    return SimpleNamespace(content=[_ToolUseBlock(tool_id, name, tool_input)], stop_reason=stop_reason)


def _proyecto_confirmado() -> Proyecto:
    p = Proyecto(nombre="placa_soporte", etapa=Etapa.ESPERANDO_CONFIRMACION_EXTRACCION)
    p.pieza_extraida = Pieza(
        pieza="placa_soporte",
        material=Material(nombre="Aluminio 6061"),
        dimensiones=Dimensiones(forma_base=FormaBase.RECTANGULAR, largo_mm=100, ancho_mm=60, espesor_mm=10),
        features=[Feature(id="f1", tipo=TipoFeature.BARRENO, diametro_mm=8, posicion=Posicion2D(x=50, y=30))],
    )
    approval.confirmar_extraccion(p)
    return p


def test_respuesta_simple_sin_herramientas():
    client = _ScriptedClient([_respuesta_texto("Hola, sube tu plano para comenzar.")])
    p = Proyecto(nombre="x")
    resultado = ejecutar_turno(p, "hola", client=client)
    assert resultado.texto_respuesta == "Hola, sube tu plano para comenzar."
    assert resultado.herramientas_ejecutadas == []
    assert len(p.mensajes) == 2  # user + assistant


def test_tool_call_exitoso_actualiza_proyecto(tmp_path, monkeypatch):
    monkeypatch.setattr(handlers.storage, "ruta_archivo_generado", lambda project_id, nombre: tmp_path / nombre)

    p = _proyecto_confirmado()
    client = _ScriptedClient(
        [
            _respuesta_tool_use("call_1", "generar_modelo_3d", {}),
            _respuesta_texto("Listo, genere el modelo 3D. Revisa la vista previa antes de continuar."),
        ]
    )
    resultado = ejecutar_turno(p, "genera el modelo 3d", client=client)

    assert resultado.herramientas_ejecutadas == ["generar_modelo_3d"]
    assert p.etapa == Etapa.ESPERANDO_CONFIRMACION_MODELO
    assert any(a.tipo == "step" for a in p.archivos)


def test_precondicion_no_cumplida_se_reporta_como_error_no_crashea():
    p = _proyecto_confirmado()  # extraccion confirmada, pero NO el modelo -> generar_trayectorias debe fallar
    client = _ScriptedClient(
        [
            _respuesta_tool_use("call_1", "generar_trayectorias", {}),
            _respuesta_texto("Aun no puedo generar trayectorias - primero confirma el modelo 3D en la interfaz."),
        ]
    )
    resultado = ejecutar_turno(p, "genera las trayectorias ya, dije que si en el chat", client=client)

    assert "confirma el modelo 3D" in resultado.texto_respuesta
    # the tool_result the model saw must flag it as an error, and the project must NOT have advanced
    tool_result_msg = p.mensajes[2]["content"][0]
    assert tool_result_msg["is_error"] is True
    assert p.modelo_confirmado is False


def test_no_llama_herramienta_desconocida_sin_crashear():
    p = Proyecto(nombre="x")
    client = _ScriptedClient(
        [
            _respuesta_tool_use("call_1", "borrar_todo_el_taller", {}),
            _respuesta_texto("No tengo esa capacidad."),
        ]
    )
    resultado = ejecutar_turno(p, "borra todo", client=client)
    assert resultado.herramientas_ejecutadas == []
    assert resultado.texto_respuesta == "No tengo esa capacidad."


def test_respeta_limite_de_iteraciones():
    respuestas = [_respuesta_tool_use(f"call_{i}", "simular_maquinado", {}) for i in range(MAX_ITERACIONES_HERRAMIENTAS)]
    client = _ScriptedClient(respuestas)
    p = Proyecto(nombre="x")
    ejecutar_turno(p, "simula una y otra vez", client=client)
    assert len(client.llamadas) == MAX_ITERACIONES_HERRAMIENTAS


def test_estado_del_proyecto_se_incluye_en_el_mensaje():
    client = _ScriptedClient([_respuesta_texto("ok")])
    p = _proyecto_confirmado()
    ejecutar_turno(p, "hola", client=client)
    contenido = client.llamadas[0]["messages"][0]["content"][0]["text"]
    assert '"pieza_confirmada": true' in contenido
