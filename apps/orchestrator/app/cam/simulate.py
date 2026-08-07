"""Capa 4 - `simular_maquinado_mastercam`.

Produces a structured summary (time, tools, warnings) from the toolpath
plan. This is NOT a physics-based gouge/collision simulation like
Mastercam Verify - it's an estimate from the Capa 5 rules engine, useful
for the human review gate but not a substitute for real simulation once
Mastercam is connected.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.cam.planner import PlanDetallado
from app.schemas.piece import Pieza


@dataclass
class ResumenSimulacion:
    tiempo_estimado_min: float | None
    numero_operaciones: int
    numero_herramientas: int
    herramientas: list[dict]
    cambios_herramienta: int
    advertencias: list[str] = field(default_factory=list)
    es_simulacion: bool = True


def simular_maquinado(pieza: Pieza, plan: PlanDetallado) -> ResumenSimulacion:
    advertencias = list(plan.plan.advertencias)
    advertencias.append(
        "Esta es una ESTIMACION basada en reglas (Capa 5), no una simulacion fisica con deteccion de "
        "colisiones/gubias como Mastercam Verify. Confirma con el maquinista antes de aprobar."
    )
    return ResumenSimulacion(
        tiempo_estimado_min=plan.plan.tiempo_estimado_min,
        numero_operaciones=len(plan.operaciones),
        numero_herramientas=len(plan.plan.herramientas),
        herramientas=plan.plan.herramientas,
        cambios_herramienta=len(plan.operaciones),
        advertencias=advertencias,
    )
