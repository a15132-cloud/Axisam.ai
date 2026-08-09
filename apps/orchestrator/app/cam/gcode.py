"""Capa 4 (Mastercam side) - `exportar_codigo_g_mastercam`.

Turns a PlanDetallado into an actual .nc file. Two honesty rules drive
every decision here, straight from the project brief:

1. Never let fabricated toolpath motion look authoritative. Where the
   cutter-center geometry is well-defined and computable (drilling with
   canned cycles; rectangular pocket clearing; edge relief clearing;
   exterior contour offsets - see cam/toolpath_geometry.py) we generate
   real motion. Where it isn't (a feature type the geometry engine itself
   couldn't build, or one missing a dimension it needs) we leave an
   explicit comment placeholder, never invented G1/G2/G3 motion.
2. Every file this function produces is stamped, top and bottom, as a
   simulation pending real Mastercam SDK verification. Capa 6 still
   requires human approval regardless, but the file itself must not be
   mistakable for verified, machine-ready code - there is still no
   gouge/collision checking across simultaneous features, no adaptive
   roughing, and plunge entries are straight (a real post would ramp or
   pre-drill).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.cam.planner import PlanDetallado
from app.cam.toolpath_geometry import (
    Punto,
    puntos_anillos_concentricos,
    puntos_contorno_exterior_circulo,
    puntos_contorno_exterior_rectangulo,
    puntos_zigzag_rectangulo,
    radio_maximo_inscrito,
    vertices_contorno_nominal_pieza,
)
from app.schemas.piece import Feature, FormaBase, Pieza, TipoFeature

DISCLAIMER = (
    "*** SIMULACION - NO VERIFICADO POR MASTERCAM REAL ***\n"
    "*** NO CARGAR EN LA MAQUINA CNC SIN REVISION DE UN MAQUINISTA ***\n"
    "*** Generado por el motor de reglas de Axiscam (Capa 5), pendiente integracion con Mastercam SDK ***"
)

FEATURES_CON_CICLO_TALADRADO = {TipoFeature.BARRENO, TipoFeature.BARRENO_ROSCADO}
FEATURES_CON_CAJERA = {TipoFeature.CAJERA, TipoFeature.RANURA}
FEATURES_CON_CONTORNO_PIEZA = {TipoFeature.PERFIL_EXTERIOR, TipoFeature.REDONDEO, TipoFeature.CHAFLAN}

FEED_PLUNGE_FRACCION = 0.5  # plunge feed is a fraction of the XY cutting feed - conservative, not tuned per material


@dataclass
class ResultadoGCode:
    contenido: str
    operaciones_con_movimiento_real: int = 0
    operaciones_solo_planeadas: int = 0
    advertencias: list[str] = field(default_factory=list)


def _comentario(pp: dict, texto: str) -> str:
    return f"{pp['comentario_apertura']}{texto}{pp['comentario_cierre']}"


def _encabezado_operacion(pp: dict, feature: Feature, op, tool_num: int) -> list[str]:
    lineas = [_comentario(pp, f"{feature.tipo.value.upper()} id={feature.id or '?'} - {op.herramienta.descripcion} - {op.estrategia}")]
    lineas.append(pp["cambio_herramienta"].format(tool=tool_num))
    lineas.append(pp["inicio_husillo"].format(rpm=int(op.parametros.rpm)))
    if op.parametros.refrigerante in ("requerido", "recomendado"):
        lineas.append(pp["refrigerante_on"])
    return lineas


def _pie_operacion(pp: dict, op) -> list[str]:
    lineas = []
    if op.parametros.refrigerante in ("requerido", "recomendado"):
        lineas.append(pp["refrigerante_off"])
    lineas.append(f"G0 Z{pp['plano_seguridad_mm']:.3f}")
    return lineas


def _bloque_taladrado(pp: dict, feature: Feature, op, espesor_pieza: float, tool_num: int) -> list[str]:
    lineas = _encabezado_operacion(pp, feature, op, tool_num)
    profundidad = op.profundidad_pasada_mm or espesor_pieza
    z_objetivo = -abs(profundidad)
    ciclo = pp["ciclo_taladrado_profundo"] if profundidad > (op.herramienta.diametro_mm * 3) else pp["ciclo_taladrado_simple"]
    retract = 3.0

    # G81/G83 are group-1 modal motion codes: once invoked on the first
    # hole, subsequent holes are drilled just by issuing a bare X/Y move -
    # NOT another G0/G1, which would silently cancel the canned cycle and
    # turn the remaining "drilled" holes into unmachined rapid moves.
    posiciones = feature.lista_posiciones()
    primera = posiciones[0]
    lineas.append(f"G0 X{primera.x:.3f} Y{primera.y:.3f}")
    lineas.append(f"G0 Z{pp['plano_seguridad_mm']:.3f}")
    lineas.append(
        f"{ciclo} G99 X{primera.x:.3f} Y{primera.y:.3f} Z{z_objetivo:.3f} R{retract:.3f} F{op.parametros.avance_mm_min:.1f}"
    )
    for pos in posiciones[1:]:
        lineas.append(f"X{pos.x:.3f} Y{pos.y:.3f}")
    lineas.append("G80")
    lineas.extend(_pie_operacion(pp, op))
    return lineas


def _pasadas_z(profundidad_pasada: float, profundidad_total: float, z_top: float = 0.0) -> list[float]:
    """Z target for each roughing pass, deepest last, clipped to the total
    requested depth (the last pass is often shallower than a full step).
    `z_top` is the Z of the top of stock for THIS operation relative to
    the part's normal Z=0 reference (its own top face) - 0.0 for every
    feature that starts cutting from the part's real top surface (the
    overwhelming majority), but nonzero for saliente/boss facing, where
    the surrounding material starts higher, at the boss's own height
    above the base plate (see _bloque_saliente).
    """
    n = max(1, math.ceil(profundidad_total / profundidad_pasada))
    return [z_top - min(profundidad_pasada * (i + 1), profundidad_total) for i in range(n)]


def _recorrer_puntos_multi_pasada(pp: dict, op, puntos: list[Punto], z_top: float = 0.0) -> list[str]:
    lineas = []
    profundidad_total = op.profundidad_total_mm or op.profundidad_pasada_mm or 1.0
    profundidad_pasada = op.profundidad_pasada_mm or profundidad_total
    lineas.append(f"G0 X{puntos[0][0]:.3f} Y{puntos[0][1]:.3f}")
    lineas.append(f"G0 Z{pp['plano_seguridad_mm']:.3f}")
    zetas = _pasadas_z(profundidad_pasada, profundidad_total, z_top)
    for i, z in enumerate(zetas):
        lineas.append(f"G1 Z{z:.3f} F{op.parametros.avance_mm_min * FEED_PLUNGE_FRACCION:.1f}")
        for x, y in puntos[1:]:
            lineas.append(f"G1 X{x:.3f} Y{y:.3f} F{op.parametros.avance_mm_min:.1f}")
        lineas.append(f"G0 Z{pp['plano_seguridad_mm']:.3f}")
        if i < len(zetas) - 1:
            lineas.append(f"G0 X{puntos[0][0]:.3f} Y{puntos[0][1]:.3f}")
    return lineas


def _bloque_cajera(pp: dict, feature: Feature, op, tool_num: int) -> tuple[list[str], bool]:
    ancho = feature.ancho_mm or 10.0
    largo = feature.largo_mm or 10.0
    lineas = _encabezado_operacion(pp, feature, op, tool_num)
    hubo_movimiento = False

    for pos in feature.lista_posiciones():
        puntos = puntos_zigzag_rectangulo(pos.x, pos.y, largo, ancho, op.herramienta.diametro_mm)
        if puntos is None:
            lineas.append(
                _comentario(
                    pp,
                    f"HERRAMIENTA {op.herramienta.diametro_mm}mm NO CABE en cajera {largo}x{ancho}mm en "
                    f"({pos.x},{pos.y}) - TRAYECTORIA NO GENERADA, requiere herramienta mas pequena",
                )
            )
            continue
        lineas.extend(_recorrer_puntos_multi_pasada(pp, op, puntos))
        hubo_movimiento = True

    lineas.extend(_pie_operacion(pp, op))
    return lineas, hubo_movimiento


def _rectangulo_relieve_borde(feature: Feature, pieza: Pieza) -> tuple[float, float, float, float] | None:
    """(cx, cy, largo_x, ancho_y) of the escalon's rectangular footprint -
    the exact same edge-strip geometry app.geometry.builder._cortar_relieve_borde
    cuts, so the toolpath clears the same area the solid model actually has
    machined away. Returns None for an unrecognized cara (mirrors the
    builder's GeometryBuildError case, but here it's just "can't route it").
    """
    d = pieza.dimensiones
    largo, ancho_pieza = d.largo_mm, d.ancho_mm
    ancho_relieve = feature.ancho_mm or 0.0
    if feature.cara == "lateral_frontal":  # Y = 0 edge
        return largo / 2, ancho_relieve / 2, largo, ancho_relieve
    if feature.cara == "lateral_posterior":  # Y = ancho edge
        return largo / 2, ancho_pieza - ancho_relieve / 2, largo, ancho_relieve
    if feature.cara == "lateral_izquierda":  # X = 0 edge
        return ancho_relieve / 2, ancho_pieza / 2, ancho_relieve, ancho_pieza
    if feature.cara == "lateral_derecha":  # X = largo edge
        return largo - ancho_relieve / 2, ancho_pieza / 2, ancho_relieve, ancho_pieza
    return None


def _bloque_escalon(pp: dict, feature: Feature, op, pieza: Pieza, tool_num: int) -> tuple[list[str], bool]:
    lineas = _encabezado_operacion(pp, feature, op, tool_num)
    # Mirror app.geometry.builder's own refusal exactly: a relief with no
    # confirmed ancho/profundidad has no cut in the STEP/STL model, so it
    # must not get real G1 motion here either (rules.py's generic
    # "guess 50% of espesor for a blind feature" fallback would otherwise
    # hand this a depth STL/STEP never got - the model and the G-code
    # would disagree about whether the part was even cut here).
    if feature.ancho_mm is None or feature.profundidad_mm is None:
        lineas.append(
            _comentario(pp, f"ESCALON id={feature.id or '?'}: falta ancho_mm y/o profundidad_mm - TRAYECTORIA NO GENERADA (tampoco se modelo en el solido)")
        )
        lineas.extend(_pie_operacion(pp, op))
        return lineas, False

    rect = _rectangulo_relieve_borde(feature, pieza)
    if rect is None:
        lineas.append(_comentario(pp, f"ESCALON id={feature.id or '?'}: cara '{feature.cara}' no reconocida - TRAYECTORIA NO GENERADA"))
        lineas.extend(_pie_operacion(pp, op))
        return lineas, False

    cx, cy, largo, ancho = rect
    puntos = puntos_zigzag_rectangulo(cx, cy, largo, ancho, op.herramienta.diametro_mm)
    if puntos is None:
        lineas.append(
            _comentario(
                pp,
                f"HERRAMIENTA {op.herramienta.diametro_mm}mm NO CABE en el ancho del relieve "
                f"({ancho}mm) en '{feature.cara}' - TRAYECTORIA NO GENERADA, requiere herramienta mas pequena",
            )
        )
        lineas.extend(_pie_operacion(pp, op))
        return lineas, False

    lineas.extend(_recorrer_puntos_multi_pasada(pp, op, puntos))
    lineas.extend(_pie_operacion(pp, op))
    return lineas, True


def _puntos_contorno_pieza(pieza: Pieza, offset: float) -> list[Punto] | None:
    d = pieza.dimensiones
    if d.forma_base == FormaBase.RECTANGULAR and d.largo_mm and d.ancho_mm:
        return puntos_contorno_exterior_rectangulo(d.largo_mm / 2, d.ancho_mm / 2, d.largo_mm, d.ancho_mm, offset)
    if d.forma_base == FormaBase.CIRCULAR and d.diametro_mm:
        return puntos_contorno_exterior_circulo(0.0, 0.0, d.diametro_mm / 2, offset)
    return None  # shouldn't happen post Capa-4 model build, but stay safe rather than crash


def _bloque_contorno(pp: dict, feature: Feature, op, pieza: Pieza, offset: float, tool_num: int) -> tuple[list[str], bool]:
    puntos = _puntos_contorno_pieza(pieza, offset)
    if puntos is None:
        return _bloque_pendiente(pp, feature, op), False

    lineas = _encabezado_operacion(pp, feature, op, tool_num)
    lineas.extend(_recorrer_puntos_multi_pasada(pp, op, puntos))
    lineas.extend(_pie_operacion(pp, op))
    return lineas, True


def _bloque_saliente(pp: dict, feature: Feature, op, pieza: Pieza, tool_num: int) -> tuple[list[str], bool]:
    """Facing/roughing the material AROUND a boss to leave it standing
    proud - the real, standard subtractive technique for this feature
    (see rules.py's planear_operacion). The facing spreads outward from
    the boss up to the largest circle that stays inside the REAL part
    boundary (radio_maximo_inscrito) - a computed limit from the actual
    geometry, not a guessed pocket size. Cuts from z_top = the boss's own
    height (raw stock starts that high) down to the base plate's normal
    top surface (z=0 in this program's convention) - see _pasadas_z.
    """
    lineas = _encabezado_operacion(pp, feature, op, tool_num)
    hubo_movimiento = False
    r_herr = op.herramienta.diametro_mm / 2
    altura_saliente = feature.profundidad_mm or 5.0

    for pos in feature.lista_posiciones():
        radio_boss = (feature.diametro_mm or 10.0) / 2

        d = pieza.dimensiones
        if d.forma_base == FormaBase.CIRCULAR and d.diametro_mm:
            radio_max = d.diametro_mm / 2 - math.hypot(pos.x, pos.y)
        else:
            vertices = vertices_contorno_nominal_pieza(pieza)
            if vertices is None:
                lineas.append(
                    _comentario(pp, f"SALIENTE id={feature.id or '?'}: forma_base no soportada para calcular el limite exterior - TRAYECTORIA NO GENERADA")
                )
                continue
            radio_max = radio_maximo_inscrito(pos.x, pos.y, vertices)

        radio_interior = radio_boss + r_herr
        radio_exterior = radio_max - r_herr
        anillos = puntos_anillos_concentricos(pos.x, pos.y, radio_interior, radio_exterior, op.herramienta.diametro_mm)
        if not anillos:
            lineas.append(
                _comentario(
                    pp,
                    f"SALIENTE id={feature.id or '?'}: sin espacio para carear alrededor con la herramienta "
                    f"{op.herramienta.diametro_mm}mm sin salirse de la pieza - TRAYECTORIA NO GENERADA, revisar manualmente",
                )
            )
            continue

        for anillo in anillos:
            lineas.extend(_recorrer_puntos_multi_pasada(pp, op, anillo, z_top=altura_saliente))
        hubo_movimiento = True

    lineas.extend(_pie_operacion(pp, op))
    return lineas, hubo_movimiento


def _bloque_pendiente(pp: dict, feature: Feature, op) -> list[str]:
    return [
        _comentario(
            pp,
            f"{feature.tipo.value.upper()} id={feature.id or '?'} - ESTRATEGIA: {op.estrategia} - "
            f"HERRAMIENTA SUGERIDA: {op.herramienta.descripcion} - "
            f"RPM~{int(op.parametros.rpm)} F~{op.parametros.avance_mm_min:.0f}mm/min",
        ),
        _comentario(pp, "TRAYECTORIA NO GENERADA - requiere Mastercam real o geometria no soportada aun"),
    ]


def generar_codigo_g(pieza: Pieza, plan: PlanDetallado, numero_programa: int = 1001) -> ResultadoGCode:
    pp = plan.postprocesador
    advertencias = list(plan.plan.advertencias)
    con_movimiento = 0
    sin_movimiento = 0

    lineas: list[str] = []
    for l in DISCLAIMER.splitlines():
        lineas.append(_comentario(pp, l))
    lineas.append(_comentario(pp, f"Pieza: {pieza.pieza} | Material: {pieza.material.nombre} | Cantidad: {pieza.cantidad}"))
    lineas.append(_comentario(pp, f"Postprocesador: {pp['nombre_display']}"))
    lineas.append(_comentario(pp, f"Generado: {datetime.now(timezone.utc).isoformat()}"))
    lineas.append("")
    lineas.append(f"{pp['numero_programa_prefijo']}{numero_programa}")
    lineas.append("G90 G54 G17 G40 G49 G80")
    lineas.append(pp["comando_unidades_mm"] if pieza.unidades == "mm" else pp["comando_unidades_pulg"])
    lineas.append(f"G0 Z{pp['plano_seguridad_mm']:.3f}")
    lineas.append("")

    tool_num = 1
    for feature, op in plan.operaciones_por_feature:
        if feature.tipo in FEATURES_CON_CICLO_TALADRADO:
            lineas.extend(_bloque_taladrado(pp, feature, op, pieza.dimensiones.espesor_mm, tool_num))
            con_movimiento += 1
        elif feature.tipo in FEATURES_CON_CAJERA:
            bloque, hubo_movimiento = _bloque_cajera(pp, feature, op, tool_num)
            lineas.extend(bloque)
            con_movimiento += 1 if hubo_movimiento else 0
            sin_movimiento += 0 if hubo_movimiento else 1
        elif feature.tipo == TipoFeature.SALIENTE:
            bloque, hubo_movimiento = _bloque_saliente(pp, feature, op, pieza, tool_num)
            lineas.extend(bloque)
            con_movimiento += 1 if hubo_movimiento else 0
            sin_movimiento += 0 if hubo_movimiento else 1
        elif feature.tipo == TipoFeature.ESCALON:
            bloque, hubo_movimiento = _bloque_escalon(pp, feature, op, pieza, tool_num)
            lineas.extend(bloque)
            con_movimiento += 1 if hubo_movimiento else 0
            sin_movimiento += 0 if hubo_movimiento else 1
        elif feature.tipo in FEATURES_CON_CONTORNO_PIEZA:
            # Cutting the part free from stock needs the tool OUTSIDE the
            # nominal boundary (offset = tool radius). A corner-round/chamfer
            # form tool creates its profile by riding the nominal edge
            # itself (offset = 0) - the fillet/chamfer comes from the tool's
            # own shape, not from how far off the line its center travels.
            offset = op.herramienta.diametro_mm / 2 if feature.tipo == TipoFeature.PERFIL_EXTERIOR else 0.0
            bloque, hubo_movimiento = _bloque_contorno(pp, feature, op, pieza, offset, tool_num)
            lineas.extend(bloque)
            con_movimiento += 1 if hubo_movimiento else 0
            sin_movimiento += 0 if hubo_movimiento else 1
        else:
            lineas.extend(_bloque_pendiente(pp, feature, op))
            sin_movimiento += 1
        lineas.append("")
        tool_num += 1

    lineas.append(_comentario(pp, "FIN DE PROGRAMA - " + DISCLAIMER.splitlines()[0]))
    lineas.append(pp["fin_programa"])

    if sin_movimiento:
        advertencias.append(
            f"{sin_movimiento} operacion(es) quedaron solo planeadas (sin trayectoria real) - "
            "ver comentarios en el archivo. Requieren Mastercam real antes de maquinar."
        )

    return ResultadoGCode(
        contenido="\n".join(lineas),
        operaciones_con_movimiento_real=con_movimiento,
        operaciones_solo_planeadas=sin_movimiento,
        advertencias=advertencias,
    )
