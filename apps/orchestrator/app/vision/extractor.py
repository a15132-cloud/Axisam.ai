"""Capa 3 - plano -> JSON estructurado, via Claude multimodal + tool use.

The pattern: define one tool whose input_schema IS the Pieza schema, force
Claude to call it (tool_choice), then validate the tool call's input
against the real Pydantic model. This keeps "what Claude can say" and
"what the rest of the pipeline accepts" as the exact same contract - no
separate free-text-then-parse step that could drift out of sync.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass

import anthropic
from pydantic import ValidationError

from app.config import settings
from app.schemas.piece import Pieza
from app.vision.dxf_reader import DXFLecturaError, resumen_textual_dxf
from app.vision.prompts import SYSTEM_PROMPT

TOOL_NAME = "registrar_pieza_extraida"

MEDIA_TYPES_IMAGEN = {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif"}


class ExtraccionError(Exception):
    pass


class FormatoNoSoportado(ExtraccionError):
    pass


@dataclass
class ResultadoExtraccion:
    pieza: Pieza
    raw_tool_input: dict
    stop_reason: str


def _tool_schema() -> dict:
    schema = Pieza.model_json_schema()
    schema.pop("example", None)
    return schema


def _build_content_blocks(contenido: bytes, media_type: str, nombre_archivo: str) -> list[dict]:
    tipo_normalizado = (media_type or "").lower()
    nombre_lower = nombre_archivo.lower()

    if tipo_normalizado in MEDIA_TYPES_IMAGEN:
        b64 = base64.standard_b64encode(contenido).decode()
        media_final = "image/jpeg" if tipo_normalizado == "image/jpg" else tipo_normalizado
        return [{"type": "image", "source": {"type": "base64", "media_type": media_final, "data": b64}}]

    if tipo_normalizado == "application/pdf" or nombre_lower.endswith(".pdf"):
        b64 = base64.standard_b64encode(contenido).decode()
        return [{"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64}}]

    if nombre_lower.endswith(".dxf"):
        try:
            resumen = resumen_textual_dxf(contenido)
        except DXFLecturaError as exc:
            raise ExtraccionError(str(exc)) from exc
        return [
            {
                "type": "text",
                "text": (
                    f"Contenido extraido de archivo DXF '{nombre_archivo}' "
                    f"(entidades vectoriales, no hay imagen renderizada):\n\n{resumen}"
                ),
            }
        ]

    if nombre_lower.endswith(".dwg"):
        raise FormatoNoSoportado(
            "Los archivos .dwg no son soportados todavia (formato binario propietario de Autodesk "
            "sin especificacion publica). Exporta el plano como DXF, PDF o imagen (PNG/JPG) desde tu "
            "software CAD y vuelve a subirlo."
        )

    raise FormatoNoSoportado(f"Tipo de archivo no soportado: '{media_type or 'desconocido'}' ({nombre_archivo})")


def extraer_pieza_desde_plano(
    contenido: bytes,
    media_type: str,
    nombre_archivo: str,
    instrucciones_usuario: str | None = None,
    client: anthropic.Anthropic | None = None,
) -> ResultadoExtraccion:
    if not settings.anthropic_api_key and client is None:
        raise ExtraccionError(
            "Falta una API key de Anthropic para leer el plano. Agrega la tuya en Configuración "
            "(arriba a la derecha) - se usa solo para esta extracción, nunca se guarda en el servidor."
        )

    content_blocks = _build_content_blocks(contenido, media_type, nombre_archivo)
    content_blocks.append(
        {
            "type": "text",
            "text": (
                "Extrae la pieza de este plano y llama a la herramienta registrar_pieza_extraida."
                + (f"\n\nInstrucciones adicionales del usuario: {instrucciones_usuario}" if instrucciones_usuario else "")
            ),
        }
    )

    active_client = client or anthropic.Anthropic(api_key=settings.anthropic_api_key)
    tool = {
        "name": TOOL_NAME,
        "description": "Registra en formato estructurado la pieza extraida del plano de ingenieria.",
        "input_schema": _tool_schema(),
    }

    # anthropic.AnthropicError (bad key, rate limit, network) is deliberately
    # left to propagate uncaught here - app/api/routes_projects.py maps it to
    # a clean, actionable HTTP error (see _http_desde_error_anthropic). This
    # used to be wrapped into a generic ExtraccionError with the raw
    # exception text, which meant a bad API key surfaced as an unreadable
    # dump of Anthropic's internal error JSON instead of "tu API key no es
    # valida" - now both the chat and extraction paths share one message.
    response = active_client.messages.create(
        model=settings.claude_model_vision,
        max_tokens=8192,
        system=SYSTEM_PROMPT,
        tools=[tool],
        tool_choice={"type": "tool", "name": TOOL_NAME},
        messages=[{"role": "user", "content": content_blocks}],
    )

    tool_use = next((b for b in response.content if b.type == "tool_use" and b.name == TOOL_NAME), None)
    if tool_use is None:
        raise ExtraccionError(
            "Claude no devolvio una extraccion estructurada para este plano. Intenta de nuevo, sube una "
            "imagen mas clara, o verifica que el archivo realmente contenga un dibujo de pieza."
        )

    try:
        pieza = Pieza.model_validate(tool_use.input)
    except ValidationError as exc:
        raise ExtraccionError(
            f"La extraccion de Claude no cumple el formato esperado de pieza: {exc}"
        ) from exc

    return ResultadoExtraccion(pieza=pieza, raw_tool_input=tool_use.input, stop_reason=response.stop_reason or "")
