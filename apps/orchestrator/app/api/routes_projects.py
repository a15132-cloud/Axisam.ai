"""REST surface for the project pipeline.

Split deliberately: pipeline-advancing actions (upload, the three approval
checkpoints, chat) are each their own endpoint rather than one generic
"do the next thing" call, because the three approval endpoints are the
actual Capa 6 safety mechanism - a UI button hits exactly one of them,
never something the chat endpoint or the agent can trigger on its own.
"""

from __future__ import annotations

import anthropic
from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel

from app.agent import approval
from app.agent.orchestrator import ejecutar_turno
from app.geometry.builder import GeometryBuildError
from app.schemas.piece import Pieza
from app.schemas.project import Etapa, Proyecto
from app.storage import files as storage
from app.tools import handlers
from app.vision.extractor import ExtraccionError, extraer_pieza_desde_plano

router = APIRouter(prefix="/api/projects", tags=["projects"])


def _cliente_de_usuario(x_anthropic_api_key: str | None) -> anthropic.Anthropic | None:
    """Bring-your-own-key: each browser can supply its own Anthropic API key
    via this header (see apps/web/src/lib/apiKey.ts) so the party running
    this backend never has to pay for every client's usage out of one
    shared key. Never persisted anywhere - used to build a throwaway
    client for this single request only, then discarded. Falls back to
    the server's own ANTHROPIC_API_KEY (if configured) when the header is
    absent, so existing single-operator/dev deployments keep working.
    """
    if x_anthropic_api_key:
        return anthropic.Anthropic(api_key=x_anthropic_api_key)
    return None


def _http_desde_error_anthropic(exc: anthropic.AnthropicError) -> HTTPException:
    """Anthropic SDK errors (bad key, no credit, rate limit, network) must
    never reach the client as a raw 500 - a wrong/expired API key is the
    single most likely failure now that BYOK means every user brings a
    different key, and "Internal Server Error" gives them nothing to act
    on. Maps to a clear, actionable message and the closest HTTP status.
    """
    if isinstance(exc, anthropic.AuthenticationError):
        return HTTPException(
            status_code=401,
            detail="Tu API key de Anthropic no es válida. Revísala en Configuración (arriba a la "
            "derecha) - probablemente tiene un espacio de más o un carácter faltante al copiarla.",
        )
    if isinstance(exc, anthropic.RateLimitError):
        return HTTPException(
            status_code=429,
            detail="Tu cuenta de Anthropic alcanzó su límite de uso o de créditos por ahora. "
            "Revisa el saldo/límites en console.anthropic.com e intenta de nuevo en un momento.",
        )
    if isinstance(exc, anthropic.PermissionDeniedError):
        return HTTPException(
            status_code=403,
            detail="Tu API key de Anthropic no tiene permiso para usar el modelo configurado. "
            "Revisa los permisos de la key en console.anthropic.com.",
        )
    return HTTPException(
        status_code=502,
        detail=f"No se pudo completar la solicitud a Anthropic ({exc.__class__.__name__}). "
        "Intenta de nuevo en un momento; si sigue fallando, revisa tu API key en Configuración.",
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
async def subir_plano(
    project_id: str,
    archivo: UploadFile = File(...),
    instrucciones: str | None = Form(None),
    x_anthropic_api_key: str | None = Header(default=None, alias="X-Anthropic-Api-Key"),
) -> Proyecto:
    proyecto = _obtener_o_404(project_id)
    contenido = await archivo.read()
    storage.guardar_plano_subido(project_id, archivo.filename or "plano", contenido)
    proyecto.archivo_plano = archivo.filename
    proyecto.etapa = Etapa.EXTRAYENDO
    proyecto.registrar_evento("Plano subido, extrayendo datos", detalle=archivo.filename)
    storage.guardar_proyecto(proyecto)

    try:
        resultado = extraer_pieza_desde_plano(
            contenido,
            archivo.content_type or "",
            archivo.filename or "plano",
            instrucciones,
            client=_cliente_de_usuario(x_anthropic_api_key),
        )
    except ExtraccionError as exc:
        proyecto.etapa = Etapa.ERROR
        proyecto.registrar_evento("Error extrayendo datos del plano", detalle=str(exc))
        storage.guardar_proyecto(proyecto)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except anthropic.AnthropicError as exc:
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
def chat(
    project_id: str,
    body: ChatBody,
    x_anthropic_api_key: str | None = Header(default=None, alias="X-Anthropic-Api-Key"),
) -> dict:
    proyecto = _obtener_o_404(project_id)
    try:
        resultado = ejecutar_turno(proyecto, body.mensaje, client=_cliente_de_usuario(x_anthropic_api_key))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except anthropic.AnthropicError as exc:
        raise _http_desde_error_anthropic(exc) from exc
    storage.guardar_proyecto(proyecto)
    return {
        "proyecto": proyecto,
        "respuesta": resultado.texto_respuesta,
        "herramientas_ejecutadas": resultado.herramientas_ejecutadas,
    }
