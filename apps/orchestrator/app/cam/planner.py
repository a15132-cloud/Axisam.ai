"""Capa 4 (Mastercam side) - trayectoria planning.

`generar_trayectoria_mastercam` in the tool spec maps to `planear_trayectoria`
here: real decisions (tool, speeds/feeds, strategy) via the Capa 5 rules
engine, per feature. This is genuinely useful output - a machinist can
review and use this plan even before any G-code exists.

What this module does NOT do: compute actual cutter-location toolpath
geometry (gouge-checked pocket clearing, contour offsetting with linking
moves, etc). That is what Mastercam's engine is for. See cam/gcode.py for
how the plan is turned into a (clearly labeled, partial) G-code file.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.knowledge_base import rules
from app.schemas.piece import Feature, Pieza
from app.schemas.project import ToolpathPlan

TIEMPO_CAMBIO_HERRAMIENTA_MIN = 0.5
TIEMPO_POSICIONAMIENTO_MIN = 0.15


@dataclass
class PlanDetallado:
    plan: ToolpathPlan
    operaciones: list[rules.OperacionRecomendada]
    postprocesador: dict
    operaciones_por_feature: list[tuple[Feature, rules.OperacionRecomendada]] = field(default_factory=list)


def planear_trayectoria(pieza: Pieza, postprocesador: str | None = None) -> PlanDetallado:
    advertencias: list[str] = []
    operaciones: list[rules.OperacionRecomendada] = []
    operaciones_por_feature: list[tuple[Feature, rules.OperacionRecomendada]] = []
    tiempo_total_min = 0.0
    herramientas_usadas: dict[str, dict] = {}

    try:
        pp = rules.obtener_postprocesador(postprocesador)
    except ValueError as exc:
        advertencias.append(str(exc))
        pp = rules.obtener_postprocesador()

    for feature in pieza.features:
        try:
            op = rules.planear_operacion(feature, pieza.material, pieza.dimensiones.espesor_mm)
        except rules.MaterialNoEncontrado as exc:
            advertencias.append(str(exc))
            continue

        operaciones.append(op)
        operaciones_por_feature.append((feature, op))
        advertencias.extend(f"[{feature.tipo.value} {feature.id or ''}] {n}" for n in op.notas)
        advertencias.extend(f"[{feature.tipo.value} {feature.id or ''}] {w}" for w in op.parametros.advertencias)

        n_instancias = max(len(feature.lista_posiciones()), 1)
        profundidad = op.profundidad_pasada_mm or pieza.dimensiones.espesor_mm
        tiempo_total_min += TIEMPO_CAMBIO_HERRAMIENTA_MIN  # una vez por operacion/herramienta
        if op.parametros.avance_mm_min > 0:
            tiempo_corte = n_instancias * (profundidad / op.parametros.avance_mm_min) * 1.4  # +40% retractos/aceleracion
        else:
            tiempo_corte = 0.0
        tiempo_total_min += tiempo_corte + n_instancias * TIEMPO_POSICIONAMIENTO_MIN

        clave_h = f"{op.herramienta.tipo}_{op.herramienta.diametro_mm}"
        if clave_h not in herramientas_usadas:
            herramientas_usadas[clave_h] = {
                "tipo": op.herramienta.tipo,
                "diametro_mm": op.herramienta.diametro_mm,
                "descripcion": op.herramienta.descripcion,
                "rpm": op.parametros.rpm,
                "avance_mm_min": op.parametros.avance_mm_min,
                "usos": 0,
            }
        herramientas_usadas[clave_h]["usos"] += n_instancias

    plan = ToolpathPlan(
        estrategia=f"{len(operaciones)} operacion(es) planeadas sobre {len(pieza.features)} feature(s)",
        herramientas=list(herramientas_usadas.values()),
        tiempo_estimado_min=round(tiempo_total_min, 2) if tiempo_total_min else None,
        operaciones=[
            {
                "feature_id": op.feature_id,
                "estrategia": op.estrategia,
                "herramienta": op.herramienta.descripcion,
                "rpm": op.parametros.rpm,
                "avance_mm_min": op.parametros.avance_mm_min,
                "refrigerante": op.parametros.refrigerante,
            }
            for op in operaciones
        ],
        advertencias=advertencias,
    )
    return PlanDetallado(
        plan=plan,
        operaciones=operaciones,
        postprocesador=pp,
        operaciones_por_feature=operaciones_por_feature,
    )
