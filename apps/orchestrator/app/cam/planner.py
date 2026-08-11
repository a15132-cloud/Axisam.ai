"""Capa 4 (Mastercam side) - trayectoria planning.

`generar_trayectoria_mastercam` in the tool spec maps to `planear_trayectoria`
here: real decisions (tool, speeds/feeds, strategy) via the Capa 5 rules
engine, per feature. This is genuinely useful output - a machinist can
review and use this plan even before any G-code exists.

What this module does NOT do: gouge/collision checking across
simultaneous features, adaptive/trochoidal roughing, or ramped tool
entry - real 2.5D cutter-center geometry for pockets and exterior
contours now lives in cam/toolpath_geometry.py and cam/gcode.py, but
without those safety/optimization layers a real CAM engine provides.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.cam.toolpath_geometry import radio_maximo_inscrito, vertices_contorno_nominal_pieza
from app.knowledge_base import rules
from app.schemas.piece import Feature, FormaBase, Pieza, TipoFeature
from app.schemas.project import ToolpathPlan

TIEMPO_CAMBIO_HERRAMIENTA_MIN = 0.5
TIEMPO_POSICIONAMIENTO_MIN = 0.15


def _espesor_efectivo(pieza: Pieza, feature: Feature) -> float:
    """Base plate thickness, plus the tallest saliente (boss) whose
    footprint covers any of this feature's positions.

    Why this matters: a pasante (through) hole planned with just the base
    espesor would come up short wherever a boss sits on top of it - the
    hole needs to clear the boss's added height too, not just the plate
    underneath. This is the CAM-planning side of the identical fix
    already applied on the geometry-model side (see
    app/geometry/builder.py's _cortar_barreno, which uses the solid's
    real bounding box instead of the base espesor for the same reason -
    two independent representations of the same part, so both needed
    their own fix).
    """
    if feature.tipo == TipoFeature.SALIENTE:
        return pieza.dimensiones.espesor_mm  # the boss's own height is its profundidad_mm, not this
    extra = 0.0
    for otro in pieza.features:
        if otro.tipo != TipoFeature.SALIENTE:
            continue
        radio_boss = (otro.diametro_mm or 10.0) / 2
        altura_boss = otro.profundidad_mm or 5.0
        for pos_boss in otro.lista_posiciones():
            for pos in feature.lista_posiciones():
                if math.hypot(pos.x - pos_boss.x, pos.y - pos_boss.y) <= radio_boss:
                    extra = max(extra, altura_boss)
    return pieza.dimensiones.espesor_mm + extra


def _holgura_disponible_saliente(pieza: Pieza, feature: Feature) -> float | None:
    """Real radial clearance between a saliente (boss) and the part's
    actual boundary - the same geometry app.cam.gcode._bloque_saliente
    uses to bound the facing toolpath, computed here too so the tool
    selected in Capa 5 actually fits before the toolpath generator has to
    reject it. None when the shape isn't one this can compute for
    (matches gcode.py's own fallback).
    """
    if feature.tipo != TipoFeature.SALIENTE:
        return None
    d = pieza.dimensiones
    holguras = []
    for pos in feature.lista_posiciones():
        radio_boss = (feature.diametro_mm or 10.0) / 2
        if d.forma_base == FormaBase.CIRCULAR and d.diametro_mm:
            radio_max = d.diametro_mm / 2 - math.hypot(pos.x, pos.y)
        else:
            vertices = vertices_contorno_nominal_pieza(pieza)
            if vertices is None:
                return None
            radio_max = radio_maximo_inscrito(pos.x, pos.y, vertices)
        holguras.append(radio_max - radio_boss)
    return min(holguras) if holguras else None


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
        # rules.MaterialNoEncontrado no se propaga desde aqui - planear_operacion
        # ya cae a un material generico conservador en vez de dejar sin
        # planear la feature completa (ver su propio docstring).
        op = rules.planear_operacion(
            feature, pieza.material, _espesor_efectivo(pieza, feature), _holgura_disponible_saliente(pieza, feature)
        )

        operaciones.append(op)
        operaciones_por_feature.append((feature, op))
        advertencias.extend(f"[{feature.tipo.value} {feature.id or ''}] {n}" for n in op.notas)
        advertencias.extend(f"[{feature.tipo.value} {feature.id or ''}] {w}" for w in op.parametros.advertencias)

        n_instancias = max(len(feature.lista_posiciones()), 1)
        profundidad_pasada = op.profundidad_pasada_mm or pieza.dimensiones.espesor_mm
        profundidad_total = op.profundidad_total_mm or profundidad_pasada
        n_pasadas_z = max(1, math.ceil(profundidad_total / profundidad_pasada)) if op.herramienta.tipo != "broca" else 1
        tiempo_total_min += TIEMPO_CAMBIO_HERRAMIENTA_MIN  # una vez por operacion/herramienta
        if op.parametros.avance_mm_min > 0:
            tiempo_corte = n_instancias * n_pasadas_z * (profundidad_pasada / op.parametros.avance_mm_min) * 1.4  # +40% retractos/aceleracion
        else:
            tiempo_corte = 0.0
        tiempo_total_min += tiempo_corte + n_instancias * n_pasadas_z * TIEMPO_POSICIONAMIENTO_MIN

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
