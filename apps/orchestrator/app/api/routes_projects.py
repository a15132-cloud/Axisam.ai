"""REST surface for the project pipeline.

Split deliberately: pipeline-advancing actions (upload, the three approval
checkpoints, chat) are each their own endpoint rather than one generic
"do the next thing" call, because the three approval endpoints are the
actual Capa 6 safety mechanism - a UI button hits exactly one of them,
never something the chat endpoint or the agent can trigger on its own.
"""

from __future__ import annotations

import logging

import anthropic
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.agent import approval
from app.agent.orchestrator import ejecutar_turno
from app.geometry.builder import GeometryBuildError
from app.schemas.piece import Pieza
from app.schemas.project import Etapa, Proyecto
from app.storage import files as storage
from app.tools import handlers
from app.vision.extractor import ExtraccionError, extraer_pieza_desde_plano

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["projects"])

# Client-facing wording deliberately never mentions "API key" or any setup
# detail - whoever is chatting with Axiscam (a shop's client) shouldn't see
# implementation jargon they can't act on, the same way a ChatGPT/Perplexity
# user never sees "upstream API key" when something goes wrong on the
# provider's end. Anthropic's own account/key configuration is entirely the
# deploying operator's responsibility (one ANTHROPIC_API_KEY in the backend's
# environment - see render.yaml) - the real exception detail still goes into
# the project's activity log (registrar_evento) for that operator to diagnose.
_MENSAJE_SERVICIO_NO_DISPONIBLE = (
    "El asistente de IA no está disponible en este momento. Contacta al equipo de soporte."
)


def _http_desde_error_anthropic(exc: anthropic.AnthropicError) -> HTTPException:
    """Anthropic SDK errors (bad/missing key, no credit, rate limit,
    network) must never reach the client as a raw 500 - that used to
    surface as an unreadable dump of the SDK's exception text. Maps to a
    professional, jargon-free message and the closest sensible HTTP status.
    """
    if isinstance(exc, anthropic.RateLimitError):
        return HTTPException(
            status_code=429,
            detail="El asistente de IA alcanzó su límite de uso por ahora. Intenta de nuevo en "
            "unos minutos.",
        )
    if isinstance(exc, (anthropic.AuthenticationError, anthropic.PermissionDeniedError)):
        return HTTPException(status_code=503, detail=_MENSAJE_SERVICIO_NO_DISPONIBLE)
    return HTTPException(
        status_code=502,
        detail="No se pudo completar la solicitud al asistente de IA. Intenta de nuevo en un momento.",
    )


class CrearProyectoBody(BaseModel):
    nombre: str = "Nuevo proyecto"


class AprobarFinalBody(BaseModel):
    aprobado_por: str


class RechazarBody(BaseModel):
    motivo: str | None = None


class ChatBody(BaseModel):
    mensaje: str


class GenerarTrayectoriasBody(BaseModel):
    postprocesador: str | None = None


def _obtener_o_404(project_id: str) -> Proyecto:
    try:
        return storage.cargar_proyecto(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("")
def crear_proyecto(body: CrearProyectoBody) -> Proyecto:
    proyecto = Proyecto(nombre=body.nombre)
    proyecto.registrar_evento("Proyecto creado")
    storage.guardar_proyecto(proyecto)
    return proyecto


@router.get("")
def listar_proyectos() -> list[Proyecto]:
    return storage.listar_proyectos()


@router.get("/{project_id}")
def obtener_proyecto(project_id: str) -> Proyecto:
    return _obtener_o_404(project_id)


@router.delete("/{project_id}")
def eliminar_proyecto(project_id: str) -> dict:
    _obtener_o_404(project_id)
    storage.eliminar_proyecto(project_id)
    return {"eliminado": True}


@router.post("/{project_id}/plano")
async def subir_plano(project_id: str, archivo: UploadFile = File(...), instrucciones: str | None = Form(None)) -> Proyecto:
    proyecto = _obtener_o_404(project_id)
    contenido = await archivo.read()
    storage.guardar_plano_subido(project_id, archivo.filename or "plano", contenido)
    proyecto.archivo_plano = archivo.filename
    proyecto.etapa = Etapa.EXTRAYENDO
    proyecto.registrar_evento("Plano subido, extrayendo datos", detalle=archivo.filename)
    storage.guardar_proyecto(proyecto)

    try:
        resultado = extraer_pieza_desde_plano(
            contenido, archivo.content_type or "", archivo.filename or "plano", instrucciones
        )
    except ExtraccionError as exc:
        proyecto.etapa = Etapa.ERROR
        proyecto.registrar_evento("Error extrayendo datos del plano", detalle=str(exc))
        storage.guardar_proyecto(proyecto)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        proyecto.etapa = Etapa.ERROR
        proyecto.registrar_evento("Servicio de IA no configurado", detalle=str(exc))
        storage.guardar_proyecto(proyecto)
        raise HTTPException(status_code=503, detail=_MENSAJE_SERVICIO_NO_DISPONIBLE) from exc
    except anthropic.AnthropicError as exc:
        _logger.error("Error de Anthropic extrayendo plano (proyecto %s): %s", project_id, exc)
        proyecto.etapa = Etapa.ERROR
        proyecto.registrar_evento("Error de Anthropic extrayendo datos del plano", detalle=str(exc))
        storage.guardar_proyecto(proyecto)
        raise _http_desde_error_anthropic(exc) from exc

    proyecto.pieza_extraida = resultado.pieza
    proyecto.etapa = Etapa.ESPERANDO_CONFIRMACION_EXTRACCION
    proyecto.registrar_evento(
        "Datos extraidos del plano - esperando confirmacion",
        detalle=f"confianza {resultado.pieza.extraccion.confianza_global:.0%}",
    )
    storage.guardar_proyecto(proyecto)
    return proyecto


@router.put("/{project_id}/pieza-extraida")
def editar_pieza_extraida(project_id: str, pieza: Pieza) -> Proyecto:
    proyecto = _obtener_o_404(project_id)
    try:
        approval.editar_extraccion(proyecto)
    except approval.TransicionInvalida as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    proyecto.pieza_extraida = pieza
    storage.guardar_proyecto(proyecto)
    return proyecto


@router.post("/{project_id}/confirmar-extraccion")
def confirmar_extraccion(project_id: str) -> Proyecto:
    proyecto = _obtener_o_404(project_id)
    try:
        approval.confirmar_extraccion(proyecto)
    except approval.TransicionInvalida as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    storage.guardar_proyecto(proyecto)
    return proyecto


@router.post("/{project_id}/generar-modelo-3d")
def generar_modelo_3d(project_id: str) -> dict:
    proyecto = _obtener_o_404(project_id)
    try:
        resultado = handlers.generar_modelo_3d(proyecto)
    except handlers.PrecondicionNoCumplida as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except GeometryBuildError as exc:
        storage.guardar_proyecto(proyecto)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    storage.guardar_proyecto(proyecto)
    return {"proyecto": proyecto, **resultado}


@router.post("/{project_id}/confirmar-modelo")
def confirmar_modelo(project_id: str) -> Proyecto:
    proyecto = _obtener_o_404(project_id)
    try:
        approval.confirmar_modelo(proyecto)
    except approval.TransicionInvalida as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    storage.guardar_proyecto(proyecto)
    return proyecto


@router.post("/{project_id}/generar-trayectorias")
def generar_trayectorias(project_id: str, body: GenerarTrayectoriasBody) -> dict:
    proyecto = _obtener_o_404(project_id)
    try:
        resultado = handlers.generar_trayectorias(proyecto, body.postprocesador)
    except handlers.PrecondicionNoCumplida as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    storage.guardar_proyecto(proyecto)
    return {"proyecto": proyecto, **resultado}


@router.post("/{project_id}/simular-maquinado")
def simular_maquinado(project_id: str) -> dict:
    proyecto = _obtener_o_404(project_id)
    try:
        resultado = handlers.simular_maquinado(proyecto)
    except handlers.PrecondicionNoCumplida as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    storage.guardar_proyecto(proyecto)
    return {"proyecto": proyecto, "simulacion": resultado}


@router.post("/{project_id}/aprobar-final")
def aprobar_final(project_id: str, body: AprobarFinalBody) -> Proyecto:
    proyecto = _obtener_o_404(project_id)
    try:
        approval.aprobar_final(proyecto, body.aprobado_por)
    except approval.TransicionInvalida as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    storage.guardar_proyecto(proyecto)
    return proyecto


@router.post("/{project_id}/rechazar")
def rechazar(project_id: str, body: RechazarBody) -> Proyecto:
    proyecto = _obtener_o_404(project_id)
    approval.rechazar(proyecto, body.motivo)
    storage.guardar_proyecto(proyecto)
    return proyecto


@router.post("/{project_id}/exportar-codigo-g")
def exportar_codigo_g(project_id: str) -> dict:
    proyecto = _obtener_o_404(project_id)
    try:
        resultado = handlers.exportar_codigo_g(proyecto)
    except handlers.PrecondicionNoCumplida as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    storage.guardar_proyecto(proyecto)
    return {"proyecto": proyecto, **resultado}


@router.post("/{project_id}/chat")
def chat(project_id: str, body: ChatBody) -> dict:
    proyecto = _obtener_o_404(project_id)
    try:
        resultado = ejecutar_turno(proyecto, body.mensaje)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=_MENSAJE_SERVICIO_NO_DISPONIBLE) from exc
    except anthropic.AnthropicError as exc:
        # Same as subir_plano below: the client only ever sees the generic
        # professional message, but the real exception must land somewhere
        # the operator can actually see it - this was missing here (unlike
        # subir_plano, which already logged it), which made a real chat
        # failure undiagnosable without server shell access.
        _logger.error("Error de Anthropic en chat (proyecto %s): %s", project_id, exc)
        proyecto.registrar_evento("Error de Anthropic en chat", detalle=str(exc))
        storage.guardar_proyecto(proyecto)
        raise _http_desde_error_anthropic(exc) from exc
    storage.guardar_proyecto(proyecto)
    return {
        "proyecto": proyecto,
        "respuesta": resultado.texto_respuesta,
        "herramientas_ejecutadas": resultado.herramientas_ejecutadas,
    }
