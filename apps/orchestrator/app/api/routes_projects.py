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
from pydantic import BaseModel, Field

from app.agent import approval
from app.agent.orchestrator import ejecutar_turno
from app.config import settings
from app.geometry.builder import GeometryBuildError
from app.integrations import windows_bridge
from app.schemas.piece import Pieza
from app.schemas.project import Etapa, Proyecto
from app.storage import files as storage
from app.tools import handlers
from app.vision.extractor import ExtraccionError, ResultadoExtraccion, extraer_primera_pasada, verificar_segunda_pasada

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


class RenombrarProyectoBody(BaseModel):
    nombre: str = Field(min_length=1, max_length=200)


def _obtener_o_404(project_id: str) -> Proyecto:
    try:
        return storage.cargar_proyecto(project_id)
    except FileNotFoundError as exc:
        # A project that genuinely never existed (or was deleted) and one
        # this instance can't see right now because its persistent disk
        # hasn't finished (re)attaching after a deploy/restart raise the
        # exact same FileNotFoundError - but they need different messages.
        # "no encontrado" reads as permanent data loss to a non-technical
        # user; the real situation for the second case is "wait a few
        # seconds, it's still there." Tell them apart with the same st_dev
        # check diagnostico_almacenamiento() uses, and only widen the
        # message when there's positive evidence storage isn't the real
        # mount right now - never on a plain "file isn't there".
        if settings.storage_dir_debe_ser_persistente and storage.diagnostico_almacenamiento()["es_punto_de_montaje"] is False:
            raise HTTPException(
                status_code=503,
                detail=(
                    "El almacenamiento del servidor todavia se esta reconectando (esto pasa justo despues "
                    "de una actualizacion del servidor). Tu proyecto no se perdio - espera unos segundos y "
                    "vuelve a intentar."
                ),
            ) from exc
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


@router.put("/{project_id}/nombre")
def renombrar_proyecto(project_id: str, body: RenombrarProyectoBody) -> Proyecto:
    proyecto = _obtener_o_404(project_id)
    nombre_limpio = body.nombre.strip()
    if not nombre_limpio:
        raise HTTPException(status_code=422, detail="El nombre no puede estar vacío.")
    proyecto.nombre = nombre_limpio
    storage.guardar_proyecto(proyecto)
    return proyecto


@router.post("/{project_id}/plano")
async def subir_plano(project_id: str, archivo: UploadFile = File(...), instrucciones: str | None = Form(None)) -> Proyecto:
    """Only the FIRST Claude pass - see extraer_primera_pasada's docstring
    for why. `proyecto.etapa` stays EXTRAYENDO (not
    ESPERANDO_CONFIRMACION_EXTRACCION yet) so the frontend knows to call
    POST .../plano/verificar next before showing the confirmation card;
    `pieza_extraida` is set right away though, as a safety net - if the
    second call never happens for any reason, the human still gets to
    review and confirm the first pass's result instead of being stuck
    (see derivarEntriesPipeline.ts on the frontend, which renders the
    confirmation card off pieza_extraida directly, not off etapa).
    """
    proyecto = _obtener_o_404(project_id)
    contenido = await archivo.read()
    storage.guardar_plano_subido(project_id, archivo.filename or "plano", contenido)
    proyecto.archivo_plano = archivo.filename
    proyecto.etapa = Etapa.EXTRAYENDO
    proyecto.registrar_evento("Plano subido, extrayendo datos", detalle=archivo.filename)
    storage.guardar_proyecto(proyecto)

    try:
        resultado = extraer_primera_pasada(
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
    proyecto.registrar_evento(
        "Primera pasada de extraccion completa, verificando...",
        detalle=f"confianza {resultado.pieza.extraccion.confianza_global:.0%}",
    )
    storage.guardar_proyecto(proyecto)
    return proyecto


@router.post("/{project_id}/plano/verificar")
def verificar_plano(project_id: str) -> Proyecto:
    """The second, independent audit pass - see verificar_segunda_pasada's
    docstring. Split into its own request (called right after .../plano
    resolves, from the same "subiendo" UI state on the frontend) so each
    individual HTTP request stays comfortably under any hosting platform's
    own proxy timeout - two real Claude calls back to back inside ONE
    request was landing right at that edge in practice, which no timeout
    configured in this app's own code can work around because it isn't
    this app's timeout to configure.
    """
    proyecto = _obtener_o_404(project_id)
    if proyecto.pieza_extraida is None or not proyecto.archivo_plano:
        raise HTTPException(
            status_code=409, detail="No hay una primera pasada de extraccion todavia para verificar en este proyecto."
        )

    ruta_plano = storage.ruta_plano_subido(project_id, proyecto.archivo_plano)
    if not ruta_plano.exists():
        raise HTTPException(status_code=404, detail="No se encontro el archivo del plano guardado para verificar.")
    contenido = ruta_plano.read_bytes()
    primera_pasada = ResultadoExtraccion(pieza=proyecto.pieza_extraida, raw_tool_input={}, stop_reason="")

    try:
        resultado = verificar_segunda_pasada(contenido, "", proyecto.archivo_plano, primera_pasada)
    except (ExtraccionError, anthropic.AnthropicError, RuntimeError) as exc:
        # The review pass is a quality upgrade, not a hard requirement (see
        # verificar_segunda_pasada) - a genuine failure here (network blip,
        # rate limit) shouldn't strand a human with an otherwise-working
        # first-pass result and no way to confirm it. Fall back to the
        # first pass and say so, instead of erroring the whole upload.
        _logger.warning("Fallo la segunda pasada de verificacion (proyecto %s): %s", project_id, exc)
        resultado = primera_pasada
        resultado.pieza.extraccion.notas = (
            (resultado.pieza.extraccion.notas or "")
            + "\n\n[La segunda pasada de verificacion no se pudo completar - este es el resultado de la primera "
            "pasada sin auditar. Revisa con especial cuidado antes de confirmar.]"
        ).strip()

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


@router.post("/{project_id}/activar-solidworks")
def activar_solidworks(project_id: str) -> dict:
    """Brings the real SOLIDWORKS document behind this model to the front
    on the user's own machine, via the local bridge (see
    app.integrations.windows_bridge). Only meaningful when the model was
    actually built by real SOLIDWORKS - a simulated model has no
    SolidWorks window to jump to.
    """
    proyecto = _obtener_o_404(project_id)
    step = next((a for a in proyecto.archivos if a.tipo == "step"), None)
    if step is None:
        raise HTTPException(status_code=409, detail="Todavia no hay un modelo 3D generado para este proyecto.")
    if step.es_simulacion:
        raise HTTPException(
            status_code=409,
            detail="Este modelo se genero con el motor simulado, no con SolidWorks real - no hay ninguna ventana de SolidWorks a la que llevarte.",
        )
    try:
        windows_bridge.activar_solidworks()
    except windows_bridge.BridgeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"activado": True}


@router.post("/{project_id}/abrir-mastercam")
def abrir_mastercam(project_id: str) -> dict:
    """Launches Mastercam on the user's own machine and best-effort opens
    the generated STEP file, via the local bridge. Unlike
    activar_solidworks, this works even for a simulated model - Mastercam
    never automated anything either way, so this is just a shortcut to
    "open the app with the file", available whenever a STEP exists.
    """
    proyecto = _obtener_o_404(project_id)
    step = next((a for a in proyecto.archivos if a.tipo == "step"), None)
    if step is None:
        raise HTTPException(status_code=409, detail="Todavia no hay un archivo STEP generado para este proyecto.")
    ruta_absoluta = storage.ruta_archivo_generado(project_id, step.nombre).resolve()
    try:
        windows_bridge.abrir_mastercam(str(ruta_absoluta))
    except windows_bridge.BridgeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"abierto": True}


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
