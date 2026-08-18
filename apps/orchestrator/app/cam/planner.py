"""Capa 4 (Mastercam side) - trayectoria planning.

`generar_trayectoria_mastercam` in the tool spec maps to `planear_trayectoria`
here: real decisions (tool, speeds/feeds, strategy) via the Capa 5 rules
engine, per feature. This is genuinely useful output - a machinist can
review and use this plan even before any G-code exists.

What this module does NOT do: adaptive/trochoidal roughing, or any 3D
tool-holder/fixture collision check - real 2.5D cutter-center geometry
for pockets and exterior contours lives in cam/toolpath_geometry.py and
cam/gcode.py (which also now ramps entries instead of plunging
straight down, see _movimientos_rampa there), but without those
optimization layers a real CAM engine provides. This module DOES flag
features whose toolpaths sit closer together than their own geometry +
assigned tool need to avoid overlapping - see
_advertencias_features_cercanas - a real, if bounded (2D, footprint-
level only), gouge-risk check.
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
        # Un saliente rectangular no tiene diametro_mm - usar la mitad de
        # la diagonal (mayor que cualquier radio real del rectangulo) como
        # radio_boss aqui es deliberadamente generoso: este calculo decide
        # si una feature cercana necesita espesor extra para no quedar
        # corta, y sobrestimar el area de influencia del boss es el lado
        # seguro (en el peor caso agrega margen de mas, nunca de menos).
        if otro.diametro_mm is not None:
            radio_boss = otro.diametro_mm / 2
        elif otro.largo_mm is not None and otro.ancho_mm is not None:
            radio_boss = math.hypot(otro.largo_mm, otro.ancho_mm) / 2
        else:
            radio_boss = 10.0
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
        # Mismo criterio conservador que _espesor_efectivo: sin diametro_mm
        # (saliente rectangular) usar la media diagonal como radio
        # equivalente - sobrestima el boss, no la holgura, que es el lado
        # seguro para una herramienta que tiene que rodearlo sin tocarlo.
        if feature.diametro_mm is not None:
            radio_boss = feature.diametro_mm / 2
        elif feature.largo_mm is not None and feature.ancho_mm is not None:
            radio_boss = math.hypot(feature.largo_mm, feature.ancho_mm) / 2
        else:
            radio_boss = 5.0
        if d.forma_base == FormaBase.CIRCULAR and d.diametro_mm:
            radio_max = d.diametro_mm / 2 - math.hypot(pos.x, pos.y)
        else:
            vertices = vertices_contorno_nominal_pieza(pieza)
            if vertices is None:
                return None
            radio_max = radio_maximo_inscrito(pos.x, pos.y, vertices)
        holguras.append(radio_max - radio_boss)
    return min(holguras) if holguras else None


def _extension_geometrica(feature: Feature) -> float | None:
    """Radius of the smallest circle centered on this feature's own
    position that contains its nominal shape - a barreno's own radius, or
    the circumscribing half-diagonal for anything rectangular (cajera,
    ranura, a rectangular saliente). None when there's nothing to measure
    a footprint from (redondeo/chaflan are corner features, not
    positioned; escalon spans a whole edge, not a point; perfil_exterior
    has no geometry of its own - see builder.py). Used only by
    _advertencias_features_cercanas below.
    """
    if feature.tipo in (TipoFeature.BARRENO, TipoFeature.BARRENO_ROSCADO):
        return (feature.diametro_mm / 2) if feature.diametro_mm else None
    if feature.tipo in (TipoFeature.CAJERA, TipoFeature.RANURA, TipoFeature.SALIENTE):
        if feature.diametro_mm:
            return feature.diametro_mm / 2
        if feature.largo_mm and feature.ancho_mm:
            return math.hypot(feature.largo_mm, feature.ancho_mm) / 2
    return None


def _advertencias_features_cercanas(operaciones_por_feature: list[tuple[Feature, rules.OperacionRecomendada]]) -> list[str]:
    """Flags any two feature INSTANCES (individual positions, so this also
    catches a too-tight pattern spacing, not just two different features)
    whose toolpaths sit closer together than their own geometry plus their
    assigned tool's radius need to avoid overlapping - the tool cutting
    one could gouge into material that belongs to, or was already removed
    by, its neighbor.

    Deliberately bounded, real 2D geometry - NOT a full 3D collision
    check (no tool holder, no fixture, no simultaneous/multi-axis motion),
    just "would these two toolpath footprints overlap". A real machinist
    still has to review the plan; this catches the case that's easy to
    miss reading a plano by eye (two features positioned close enough
    that only their combined tool clearance, not the features' own
    outlines, actually overlaps).
    """
    instancias: list[tuple[Feature, object, float]] = []
    for feature, op in operaciones_por_feature:
        extension = _extension_geometrica(feature)
        if extension is None:
            continue
        envolvente = extension + op.herramienta.diametro_mm / 2
        for pos in feature.lista_posiciones():
            instancias.append((feature, pos, envolvente))

    advertencias = []
    for i in range(len(instancias)):
        f1, pos1, env1 = instancias[i]
        for j in range(i + 1, len(instancias)):
            f2, pos2, env2 = instancias[j]
            distancia = math.hypot(pos1.x - pos2.x, pos1.y - pos2.y)
            distancia_segura = env1 + env2
            if distancia < distancia_segura:
                advertencias.append(
                    f"POSIBLE CHOQUE: {f1.tipo.value} (id={f1.id or '?'}) en ({pos1.x:.1f},{pos1.y:.1f}) y "
                    f"{f2.tipo.value} (id={f2.id or '?'}) en ({pos2.x:.1f},{pos2.y:.1f}) estan a {distancia:.1f}mm "
                    f"de distancia, pero sus trayectorias con herramienta necesitan al menos {distancia_segura:.1f}mm "
                    "de separacion para no traslaparse - revisar manualmente antes de maquinar."
                )
    return advertencias


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

    advertencias.extend(_advertencias_features_cercanas(operaciones_por_feature))

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
