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
from app.vision.prompts import SYSTEM_PROMPT, VERIFICATION_SYSTEM_PROMPT

TOOL_NAME = "registrar_pieza_extraida"
TOOL_DESCRIPTION = "Registra en formato estructurado la pieza extraida del plano de ingenieria."

MEDIA_TYPES_IMAGEN = {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif"}
EXTENSION_A_MEDIA_TYPE_IMAGEN = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


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

    extension_imagen = next((ext for ext in EXTENSION_A_MEDIA_TYPE_IMAGEN if nombre_lower.endswith(ext)), None)
    if tipo_normalizado in MEDIA_TYPES_IMAGEN or extension_imagen:
        # Falls back to the extension when media_type is missing/generic -
        # needed when re-reading an already-saved plano from disk (the
        # verification pass's own HTTP request, see routes_projects.py)
        # where there's no browser-supplied Content-Type to rely on anymore.
        media_final = EXTENSION_A_MEDIA_TYPE_IMAGEN.get(extension_imagen, tipo_normalizado)
        if media_final == "image/jpg":
            media_final = "image/jpeg"
        b64 = base64.standard_b64encode(contenido).decode()
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

    raise FormatoNoSoportado(
        f"No se puede leer '{nombre_archivo}' (tipo '{media_type or 'desconocido'}'). Formatos soportados: "
        "imagenes (PNG, JPG, WEBP, GIF), PDF, y DXF. Si tu plano esta en otro formato (DWG, Word, Excel, etc.), "
        "expórtalo como PDF o imagen desde tu software y vuelve a subirlo."
    )


def _llamar_registrar_pieza(
    active_client: anthropic.Anthropic, system_prompt: str, content_blocks: list[dict]
) -> ResultadoExtraccion:
    tool = {"name": TOOL_NAME, "description": TOOL_DESCRIPTION, "input_schema": _tool_schema()}

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
        system=system_prompt,
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


def _verificar_y_refinar(
    active_client: anthropic.Anthropic, content_blocks_plano: list[dict], primera_pasada: ResultadoExtraccion
) -> ResultadoExtraccion:
    """Second, independent pass: hand the SAME plano back to Claude along
    with the first pass's JSON and have it actively audit that JSON
    against the drawing (see VERIFICATION_SYSTEM_PROMPT for exactly what
    it hunts for). This is not re-extraction from scratch - it exists
    because a real client drawing showed that a single pass can miss a
    real, continuous feature while everything else about the result still
    looks complete and plausible; the miss only surfaced on a slower,
    deliberate second read. Any failure here (bad JSON, no tool call)
    falls back to the first pass rather than losing a working result over
    the review step - this is a quality upgrade, not a hard requirement.
    """
    content_blocks = list(content_blocks_plano)
    content_blocks.append(
        {
            "type": "text",
            "text": (
                "Este es el JSON que una primera pasada extrajo de este mismo plano. Auditalo segun tus "
                "instrucciones y llama a registrar_pieza_extraida con el resultado final:\n\n"
                f"{primera_pasada.pieza.model_dump_json(indent=2)}"
            ),
        }
    )
    try:
        return _llamar_registrar_pieza(active_client, VERIFICATION_SYSTEM_PROMPT, content_blocks)
    except ExtraccionError:
        return primera_pasada


def _cliente_anthropic(client: anthropic.Anthropic | None) -> anthropic.Anthropic:
    if not settings.anthropic_api_key and client is None:
        # RuntimeError, not ExtraccionError: this is an operator/deployment
        # misconfiguration (see app/api/routes_projects.py), not something
        # about the plano itself - it must never be shown to the end client
        # verbatim the way genuine extraction errors below are.
        raise RuntimeError(
            "ANTHROPIC_API_KEY no esta configurada en el servidor - define esa variable de entorno "
            "en el despliegue del backend (ver render.yaml) para poder leer planos."
        )
    # Same reasoning as app/agent/orchestrator.py::ejecutar_turno - more
    # retry headroom for a shared key under concurrent load from many clients.
    # timeout=60: the SDK's own default (600s) plus 5 retries has no
    # realistic ceiling - a genuinely stuck call could hang long past
    # whatever the frontend is willing to wait, so the user sees "nada
    # pasa" while the backend is still silently retrying minutes later.
    # 60s per attempt is generous for a single vision call (even with
    # extended thinking) and keeps the worst case bounded and predictable
    # instead of open-ended.
    return client or anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=5, timeout=60.0)


def extraer_primera_pasada(
    contenido: bytes,
    media_type: str,
    nombre_archivo: str,
    instrucciones_usuario: str | None = None,
    client: anthropic.Anthropic | None = None,
) -> ResultadoExtraccion:
    """Just the first Claude call (no verification pass) - split out from
    extraer_pieza_desde_plano so app/api/routes_projects.py can run each
    pass as its OWN HTTP request instead of one request blocking for both.
    A real plano can take 20-40s per pass; two sequential calls inside a
    single request landed right at the edge of Render's own proxy timeout
    (independent of any timeout configured in this app's own code) - a
    request that occasionally lands just past that limit gets killed by
    the platform itself, and the client sees a bare 502 with no way to
    tell "still working" from "actually failed". Splitting into two
    requests keeps each one comfortably under any reasonable proxy limit.
    """
    active_client = _cliente_anthropic(client)
    content_blocks_plano = _build_content_blocks(contenido, media_type, nombre_archivo)
    content_blocks = list(content_blocks_plano)
    content_blocks.append(
        {
            "type": "text",
            "text": (
                "Extrae la pieza de este plano y llama a la herramienta registrar_pieza_extraida."
                + (f"\n\nInstrucciones adicionales del usuario: {instrucciones_usuario}" if instrucciones_usuario else "")
            ),
        }
    )
    return _llamar_registrar_pieza(active_client, SYSTEM_PROMPT, content_blocks)


def verificar_segunda_pasada(
    contenido: bytes,
    media_type: str,
    nombre_archivo: str,
    primera_pasada: ResultadoExtraccion,
    client: anthropic.Anthropic | None = None,
) -> ResultadoExtraccion:
    """The independent audit pass, as its own function/HTTP call - see
    extraer_primera_pasada's docstring for why this is split out. Rebuilds
    the same content blocks from the plano bytes (cheap, local, no network
    cost) since this runs as a genuinely separate request/process from the
    first pass and can't rely on holding anything in memory between them.
    """
    active_client = _cliente_anthropic(client)
    content_blocks_plano = _build_content_blocks(contenido, media_type, nombre_archivo)
    return _verificar_y_refinar(active_client, content_blocks_plano, primera_pasada)


def extraer_pieza_desde_plano(
    contenido: bytes,
    media_type: str,
    nombre_archivo: str,
    instrucciones_usuario: str | None = None,
    client: anthropic.Anthropic | None = None,
) -> ResultadoExtraccion:
    """Convenience wrapper that runs both passes back to back - used by
    tests and any non-HTTP caller. The real upload endpoint calls
    extraer_primera_pasada and verificar_segunda_pasada separately instead
    (see their docstrings) so each one is its own HTTP request.
    """
    active_client = _cliente_anthropic(client)
    primera_pasada = extraer_primera_pasada(contenido, media_type, nombre_archivo, instrucciones_usuario, active_client)
    return verificar_segunda_pasada(contenido, media_type, nombre_archivo, primera_pasada, active_client)
