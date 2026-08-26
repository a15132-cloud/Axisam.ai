"""Capa 6 - the mandatory human checkpoints.

These transitions are deliberately NOT tools the LLM can call. They are
plain functions invoked only from dedicated REST endpoints that the
frontend hits when a human clicks an explicit "Confirmar" button. The
agent's tool-use loop can explain, summarize, and nudge the user toward
confirming - it can never flip these flags itself. That split is the
actual safety mechanism, not a prompt instruction that asks the model
nicely not to skip the gate.

Axiscam's product scope is deliberately CAD only now (plano -> confirmed
data -> STEP/STL) - it no longer plans toolpaths or generates G-code (see
app/cam/*.py's own docstrings: that engine still exists and is still
tested, it's just not wired into this approval flow or the agent's tools
anymore). So there are two checkpoints, not three: confirming the
extraction, then confirming the model - which is also the final state.
"""

from __future__ import annotations

from app.schemas.project import Etapa, Proyecto


class TransicionInvalida(Exception):
    pass


def confirmar_extraccion(proyecto: Proyecto) -> Proyecto:
    if proyecto.etapa != Etapa.ESPERANDO_CONFIRMACION_EXTRACCION:
        raise TransicionInvalida(
            f"No se puede confirmar la extraccion desde la etapa '{proyecto.etapa.value}'"
        )
    if proyecto.pieza_extraida is None:
        raise TransicionInvalida("No hay datos extraidos del plano para confirmar")
    proyecto.pieza_confirmada = True
    proyecto.etapa = Etapa.MODELANDO
    proyecto.registrar_evento("Medidas y material confirmados por el usuario")
    return proyecto


def editar_extraccion(proyecto: Proyecto) -> Proyecto:
    """User is about to hand-edit the extracted JSON rather than confirm
    as-is. Stay on the same checkpoint - the caller updates pieza_extraida
    separately and the human still has to confirm afterward."""
    if proyecto.etapa != Etapa.ESPERANDO_CONFIRMACION_EXTRACCION:
        raise TransicionInvalida(f"No se puede editar la extraccion desde la etapa '{proyecto.etapa.value}'")
    proyecto.registrar_evento("Usuario edito los datos extraidos del plano")
    return proyecto


def confirmar_modelo(proyecto: Proyecto) -> Proyecto:
    """Second and now LAST checkpoint - the STEP/STL already exist (built
    before this call, gated on checkpoint 1), so confirming the model is
    confirming the final deliverable. No more toolpath/G-code stage
    follows this one - see this module's docstring.
    """
    if proyecto.etapa != Etapa.ESPERANDO_CONFIRMACION_MODELO:
        raise TransicionInvalida(
            f"No se puede confirmar el modelo 3D desde la etapa '{proyecto.etapa.value}'"
        )
    proyecto.modelo_confirmado = True
    proyecto.etapa = Etapa.APROBADO
    proyecto.registrar_evento("Modelo 3D confirmado por el usuario - proyecto listo")
    return proyecto


def rechazar(proyecto: Proyecto, motivo: str | None = None) -> Proyecto:
    proyecto.etapa = Etapa.RECHAZADO
    proyecto.registrar_evento("Proyecto rechazado por el usuario", detalle=motivo)
    return proyecto
