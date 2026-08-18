"""Capa 4 (Mastercam side) - `exportar_codigo_g_mastercam`.

Turns a PlanDetallado into an actual .nc file. Two honesty rules drive
every decision here, straight from the project brief:

1. Never let fabricated toolpath motion look authoritative. Where the
   cutter-center geometry is well-defined and computable (drilling with
   canned cycles; rectangular pocket clearing; edge relief clearing;
   exterior contour offsets - see cam/toolpath_geometry.py) we generate
   real motion. Where it isn't (a feature type the geometry engine itself
   couldn't build, one missing a dimension it needs, or one whose real
   cutting axis this generator can't safely assume - e.g. a barreno drilled
   into a side face, see _es_barreno_lateral: its real axis is +/-X or
   +/-Y, not Z, and needs machine reorientation this generator has no way
   to know is available) we leave an explicit comment placeholder, never
   invented G1/G2/G3 motion.
2. Every file this function produces is stamped, top and bottom, as a
   simulation pending real Mastercam SDK verification. Capa 6 still
   requires human approval regardless, but the file itself must not be
   mistakable for verified, machine-ready code.

   Two specific gaps a real customer flagged directly are covered now:
   entries into a pocket/contour/saliente-facing pass are ramped (angled
   descent along the path's own first segment, see _movimientos_rampa),
   not a straight Z-only plunge - drilling cycles (G81/G83) are
   unaffected, a twist drill is designed to cut on-center. And
   app.cam.planner._advertencias_features_cercanas flags any two
   features whose toolpath footprints (own geometry + assigned tool
   radius) are closer together than they need to be to avoid overlapping.

   What's still NOT here, on purpose - this is real 2D geometry, not a
   full CAM verification suite: no 3D tool-holder/fixture collision
   check, no simultaneous-motion/multi-axis interference check, no
   adaptive roughing. This file has never been run through a real
   Mastercam post-processor or cut an actual piece of material - see
   DISCLAIMER below, and Capa 6's mandatory human approval before export.
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
ANGULO_RAMPA_GRADOS = 3.0  # conservative ramp-entry angle - real roughing entries typically run 1-3 degrees


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


def _es_barreno_lateral(feature: Feature) -> bool:
    return bool(feature.cara and feature.cara.startswith("lateral"))


def _bloque_taladrado(pp: dict, feature: Feature, op, espesor_pieza: float, tool_num: int) -> tuple[list[str], list[str]]:
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

    advertencias_feature: list[str] = []
    if feature.tipo == TipoFeature.BARRENO_ROSCADO:
        # This cycle only ever cuts the PILOT hole (the tap-drill diameter
        # rules.py already sized correctly from the machuelos catalog) -
        # it is not a tapping cycle. A real rigid-tap cycle (G84) needs the
        # thread's pitch to set the correct feed/rev relationship, and the
        # schema only carries `rosca` as free text (not a validated pitch
        # field), so generating G84 here would mean parsing an arbitrary
        # string into a number that drives a physical tool - if that parse
        # were ever wrong, this cycle would break a tap or ruin the thread.
        # Emitting a real-looking G84 that's silently wrong is worse than
        # what this used to do (nothing at all): flag it loud, in-file AND
        # in advertencias, so a human adds the tapping operation instead of
        # trusting this file to have roscado a hole it only drilled.
        advertencias_feature.append(
            f"barreno_roscado {feature.rosca or ''} (id={feature.id or '?'}): este archivo SOLO genero el "
            "pretaladro - falta el ciclo de machuelo/roscado (G84 u equivalente). No lo uses para roscar sin "
            "agregar esa operacion manualmente en Mastercam."
        )
    if feature.chaflanes_compuestos:
        # The geometry engine DOES cut the multi-stage countersink into the
        # STEP/STL (see app.geometry.builder._cortar_chaflanes_compuestos) -
        # but nothing in this CAM layer knows about that field, so the
        # G-code silently drills only the straight bore and never touches
        # the countersink at all. A real countersink toolpath needs a tool
        # matched to each stage's own half-angle, possibly several tool
        # changes - genuine multi-operation CAM work, not something to
        # improvise here. Disclose it exactly like the tapping gap above,
        # rather than let a model that LOOKS fully machined (real motion,
        # no warnings) silently leave the countersink unmachined.
        etapas = ", ".join(f"{s.profundidad_mm}mm/{s.angulo_grados}g" for s in feature.chaflanes_compuestos)
        advertencias_feature.append(
            f"{feature.tipo.value} (id={feature.id or '?'}): tiene avellanado compuesto ({etapas}) modelado en "
            "el STEP/STL, pero este archivo de codigo G SOLO taladro el barreno recto - el avellanado no tiene "
            "trayectoria generada, requiere programarse manualmente en Mastercam con la herramienta de angulo correcta."
        )
    for advertencia in advertencias_feature:
        lineas.append(_comentario(pp, "*** " + advertencia + " ***"))

    lineas.extend(_pie_operacion(pp, op))
    return lineas, advertencias_feature


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


def _movimientos_rampa(pp: dict, op, punto_a: Punto, punto_b: Punto, z_inicio: float, z_fin: float) -> list[str]:
    """Ramped (angled) entry from z_inicio down to z_fin, zigzagging along
    the punto_a<->punto_b segment instead of plunging straight down on
    Z alone. A twist drill cuts on-center by design (see _bloque_taladrado,
    which correctly uses G81/G83 and is NOT touched by this) but most end
    mills are not rated for that - a straight G1 Z-only plunge (the
    previous behavior here) risks snapping the tool on anything but a very
    soft material or a very shallow pass. Always ends back at punto_a (an
    even number of traverses) so the caller's full-path pass can proceed
    from there unchanged.

    Scope note: this is entry motion only, computed from the two points of
    the toolpath's own first segment - it doesn't know about any OTHER
    feature's geometry, so it cannot by itself prevent a ramp from
    crossing into a neighboring feature's material. See
    planner._advertencias_features_cercanas for the (separate, 2D,
    footprint-level) check for that.
    """
    dx, dy = punto_b[0] - punto_a[0], punto_b[1] - punto_a[1]
    longitud_segmento = math.hypot(dx, dy)
    profundidad = z_inicio - z_fin  # positive: descending
    feed_rampa = op.parametros.avance_mm_min * FEED_PLUNGE_FRACCION
    if longitud_segmento < 0.01 or profundidad <= 0:
        # No usable XY room to ramp into (a degenerate single-point path,
        # or nothing to descend) - fall back to the old straight plunge,
        # but say so, rather than silently doing the one thing this
        # function exists to avoid.
        lineas = [f"G1 Z{z_fin:.3f} F{feed_rampa:.1f}"]
        if longitud_segmento < 0.01 and profundidad > 0:
            lineas.insert(0, _comentario(pp, "sin espacio en XY para rampa - entrada recta (revisar manualmente)"))
        return lineas

    dz_por_traverso = longitud_segmento * math.tan(math.radians(ANGULO_RAMPA_GRADOS))
    n_traversos = max(1, math.ceil(profundidad / dz_por_traverso))
    if n_traversos % 2 == 1:
        n_traversos += 1  # par, para que el ultimo movimiento termine de vuelta en punto_a

    lineas = []
    for i in range(n_traversos):
        z = z_inicio - profundidad * (i + 1) / n_traversos
        destino = punto_b if i % 2 == 0 else punto_a
        lineas.append(f"G1 X{destino[0]:.3f} Y{destino[1]:.3f} Z{z:.3f} F{feed_rampa:.1f}")
    return lineas


def _recorrer_puntos_multi_pasada(pp: dict, op, puntos: list[Punto], z_top: float = 0.0) -> list[str]:
    lineas = []
    profundidad_total = op.profundidad_total_mm or op.profundidad_pasada_mm or 1.0
    profundidad_pasada = op.profundidad_pasada_mm or profundidad_total
    lineas.append(f"G0 X{puntos[0][0]:.3f} Y{puntos[0][1]:.3f}")
    lineas.append(f"G0 Z{pp['plano_seguridad_mm']:.3f}")
    lineas.append(f"G0 Z{z_top:.3f}")  # rapid down to the top of stock - still in air, not yet cutting
    zetas = _pasadas_z(profundidad_pasada, profundidad_total, z_top)
    punto_rampa_b = puntos[1] if len(puntos) > 1 else puntos[0]
    for i, z in enumerate(zetas):
        lineas.extend(_movimientos_rampa(pp, op, puntos[0], punto_rampa_b, z_top, z))
        for x, y in puntos[1:]:
            lineas.append(f"G1 X{x:.3f} Y{y:.3f} F{op.parametros.avance_mm_min:.1f}")
        lineas.append(f"G0 Z{pp['plano_seguridad_mm']:.3f}")
        if i < len(zetas) - 1:
            lineas.append(f"G0 X{puntos[0][0]:.3f} Y{puntos[0][1]:.3f}")
            lineas.append(f"G0 Z{z_top:.3f}")
    return lineas


def _encabezado_id(pp: dict, feature: Feature, op) -> str:
    return _comentario(pp, f"{feature.tipo.value.upper()} id={feature.id or '?'} - {op.herramienta.descripcion} - {op.estrategia}")


def _bloque_cajera(pp: dict, feature: Feature, op, tool_num: int) -> tuple[list[str], bool]:
    ancho = feature.ancho_mm or 10.0
    largo = feature.largo_mm or 10.0
    cuerpo: list[str] = []
    hubo_movimiento = False

    for pos in feature.lista_posiciones():
        puntos = puntos_zigzag_rectangulo(pos.x, pos.y, largo, ancho, op.herramienta.diametro_mm)
        if puntos is None:
            cuerpo.append(
                _comentario(
                    pp,
                    f"HERRAMIENTA {op.herramienta.diametro_mm}mm NO CABE en cajera {largo}x{ancho}mm en "
                    f"({pos.x},{pos.y}) - TRAYECTORIA NO GENERADA, requiere herramienta mas pequena",
                )
            )
            continue
        cuerpo.extend(_recorrer_puntos_multi_pasada(pp, op, puntos))
        hubo_movimiento = True

    if not hubo_movimiento:
        # No position machined at all - do not stage a tool change/spindle
        # start/coolant-on around a cut that never happens (see _bloque_escalon's
        # docstring on the same principle: a real machinist reading this file
        # should never see the machine "get ready" for nothing).
        return [_encabezado_id(pp, feature, op), *cuerpo], False

    lineas = _encabezado_operacion(pp, feature, op, tool_num)
    lineas.extend(cuerpo)
    lineas.extend(_pie_operacion(pp, op))
    return lineas, True


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
    """A block with nothing to cut must not stage the machine for a cut -
    no tool change, no spindle start, no coolant on/off around empty air.
    Every early-return here is deliberately just the identifying comment
    line plus the reason, exactly what _bloque_pendiente already does for
    a fully-unsupported feature type - a real machinist reading this file
    should never see the machine "get ready" for a cut that never happens.
    """
    # Mirror app.geometry.builder's own refusal exactly: a relief with no
    # confirmed ancho/profundidad has no cut in the STEP/STL model, so it
    # must not get real G1 motion here either (rules.py's generic
    # "guess 50% of espesor for a blind feature" fallback would otherwise
    # hand this a depth STL/STEP never got - the model and the G-code
    # would disagree about whether the part was even cut here).
    if feature.ancho_mm is None or feature.profundidad_mm is None:
        return [
            _encabezado_id(pp, feature, op),
            _comentario(pp, "TRAYECTORIA NO GENERADA: falta ancho_mm y/o profundidad_mm (tampoco se modelo en el solido)"),
        ], False

    rect = _rectangulo_relieve_borde(feature, pieza)
    if rect is None:
        return [
            _encabezado_id(pp, feature, op),
            _comentario(pp, f"TRAYECTORIA NO GENERADA: cara '{feature.cara}' no reconocida"),
        ], False

    cx, cy, largo, ancho = rect
    puntos = puntos_zigzag_rectangulo(cx, cy, largo, ancho, op.herramienta.diametro_mm)
    if puntos is None:
        return [
            _encabezado_id(pp, feature, op),
            _comentario(
                pp,
                f"TRAYECTORIA NO GENERADA: herramienta {op.herramienta.diametro_mm}mm no cabe en el ancho "
                f"del relieve ({ancho}mm) en '{feature.cara}', requiere herramienta mas pequena",
            ),
        ], False

    lineas = _encabezado_operacion(pp, feature, op, tool_num)
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
    cuerpo: list[str] = []
    hubo_movimiento = False
    r_herr = op.herramienta.diametro_mm / 2
    altura_saliente = feature.profundidad_mm or 5.0

    if feature.diametro_mm is None:
        # Saliente rectangular/prismatico (largo_mm/ancho_mm en vez de
        # diametro_mm - ver Feature._validate_shape_params) - el careado
        # de anillos concentricos de aqui abajo solo sabe rodear un boss
        # circular. Un boss rectangular necesitaria una estrategia de
        # careado distinta (una isla rectangular, no un anillo), que este
        # motor todavia no genera - omitir con una nota clara es mejor que
        # cortar anillos alrededor de un radio inventado que no corresponde
        # a la forma real de la pieza.
        return [
            _encabezado_id(pp, feature, op),
            _comentario(
                pp,
                f"SALIENTE id={feature.id or '?'}: boss rectangular (no circular) - el careado automatico "
                "todavia solo soporta salientes circulares. TRAYECTORIA NO GENERADA, modelar manualmente.",
            ),
        ], False

    for pos in feature.lista_posiciones():
        radio_boss = feature.diametro_mm / 2

        d = pieza.dimensiones
        if d.forma_base == FormaBase.CIRCULAR and d.diametro_mm:
            radio_max = d.diametro_mm / 2 - math.hypot(pos.x, pos.y)
        else:
            vertices = vertices_contorno_nominal_pieza(pieza)
            if vertices is None:
                cuerpo.append(
                    _comentario(pp, f"SALIENTE id={feature.id or '?'}: forma_base no soportada para calcular el limite exterior - TRAYECTORIA NO GENERADA")
                )
                continue
            radio_max = radio_maximo_inscrito(pos.x, pos.y, vertices)

        radio_interior = radio_boss + r_herr
        radio_exterior = radio_max - r_herr
        anillos = puntos_anillos_concentricos(pos.x, pos.y, radio_interior, radio_exterior, op.herramienta.diametro_mm)
        if not anillos:
            cuerpo.append(
                _comentario(
                    pp,
                    f"SALIENTE id={feature.id or '?'}: sin espacio para carear alrededor con la herramienta "
                    f"{op.herramienta.diametro_mm}mm sin salirse de la pieza - TRAYECTORIA NO GENERADA, revisar manualmente",
                )
            )
            continue

        for anillo in anillos:
            cuerpo.extend(_recorrer_puntos_multi_pasada(pp, op, anillo, z_top=altura_saliente))
        hubo_movimiento = True

    if not hubo_movimiento:
        return [_encabezado_id(pp, feature, op), *cuerpo], False

    lineas = _encabezado_operacion(pp, feature, op, tool_num)
    lineas.extend(cuerpo)
    lineas.extend(_pie_operacion(pp, op))
    return lineas, True


def _bloque_pendiente(pp: dict, feature: Feature, op, razon: str | None = None) -> list[str]:
    return [
        _comentario(
            pp,
            f"{feature.tipo.value.upper()} id={feature.id or '?'} - ESTRATEGIA: {op.estrategia} - "
            f"HERRAMIENTA SUGERIDA: {op.herramienta.descripcion} - "
            f"RPM~{int(op.parametros.rpm)} F~{op.parametros.avance_mm_min:.0f}mm/min",
        ),
        _comentario(pp, f"TRAYECTORIA NO GENERADA: {razon}" if razon else "TRAYECTORIA NO GENERADA - requiere Mastercam real o geometria no soportada aun"),
    ]


def generar_codigo_g(pieza: Pieza, plan: PlanDetallado, numero_programa: int = 1001) -> ResultadoGCode:
    pp = plan.postprocesador
    advertencias = list(plan.plan.advertencias)
    con_movimiento = 0
    sin_movimiento = 0
    pendientes: list[str] = []

    # Operations are built BEFORE the header on purpose: whether any
    # operation ended up with no real toolpath is only known after running
    # the loop, and a machinist must never have to scroll past real G-code
    # to discover that a real cut - one they might expect their part to
    # have - was silently skipped. See the block appended into the header
    # below: if pendientes is non-empty, it becomes the very first thing
    # in the file, before even the postprocessor/date info.
    lineas_operaciones: list[str] = []
    tool_num = 1
    for feature, op in plan.operaciones_por_feature:
        if feature.tipo in FEATURES_CON_CICLO_TALADRADO and _es_barreno_lateral(feature):
            # _bloque_taladrado only ever drills straight down -Z with a
            # canned cycle (G81/G83) - correct for the overwhelming
            # majority of barrenos, but geometrically wrong for one drilled
            # into a side face (see app.geometry.builder.CARAS_LATERALES,
            # added for real lateral-face drilling on the model side): the
            # hole's real axis there is +/-X or +/-Y, not Z, and cutting it
            # would need the machine reoriented (4th-axis indexer or an
            # angle head) that this generator has no way to know is even
            # available. Emitting a Z-down cycle at the hole's (x, y) would
            # be real-looking G-code that cuts in the wrong place on the
            # wrong axis - worse than not generating it. Route it to the
            # same explicit "not generated" path as any other feature this
            # generator genuinely can't route yet, exactly like a barreno
            # missing a diametro would fall through elsewhere.
            lineas_operaciones.extend(
                _bloque_pendiente(
                    pp,
                    feature,
                    op,
                    razon=(
                        f"perforacion en cara '{feature.cara}' - este generador solo produce ciclos de "
                        "taladrado rectos en Z, requiere 4to eje/cabezal angular o programarse manualmente en Mastercam"
                    ),
                )
            )
            hubo_movimiento = False
            sin_movimiento += 1
        elif feature.tipo in FEATURES_CON_CICLO_TALADRADO:
            bloque, advertencias_taladrado = _bloque_taladrado(pp, feature, op, pieza.dimensiones.espesor_mm, tool_num)
            lineas_operaciones.extend(bloque)
            advertencias.extend(advertencias_taladrado)
            con_movimiento += 1
            hubo_movimiento = True
        elif feature.tipo in FEATURES_CON_CAJERA:
            bloque, hubo_movimiento = _bloque_cajera(pp, feature, op, tool_num)
            lineas_operaciones.extend(bloque)
            con_movimiento += 1 if hubo_movimiento else 0
            sin_movimiento += 0 if hubo_movimiento else 1
        elif feature.tipo == TipoFeature.SALIENTE:
            bloque, hubo_movimiento = _bloque_saliente(pp, feature, op, pieza, tool_num)
            lineas_operaciones.extend(bloque)
            con_movimiento += 1 if hubo_movimiento else 0
            sin_movimiento += 0 if hubo_movimiento else 1
        elif feature.tipo == TipoFeature.ESCALON:
            bloque, hubo_movimiento = _bloque_escalon(pp, feature, op, pieza, tool_num)
            lineas_operaciones.extend(bloque)
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
            lineas_operaciones.extend(bloque)
            con_movimiento += 1 if hubo_movimiento else 0
            sin_movimiento += 0 if hubo_movimiento else 1
        else:
            lineas_operaciones.extend(_bloque_pendiente(pp, feature, op))
            hubo_movimiento = False
            sin_movimiento += 1
        if not hubo_movimiento:
            pendientes.append(f"{feature.tipo.value.upper()} id={feature.id or '?'}")
        lineas_operaciones.append("")
        tool_num += 1

    lineas: list[str] = []
    for l in DISCLAIMER.splitlines():
        lineas.append(_comentario(pp, l))
    if pendientes:
        lineas.append(_comentario(pp, "*" * 60))
        lineas.append(_comentario(pp, f"*** ATENCION: {len(pendientes)} OPERACION(ES) SIN CORTAR EN ESTE ARCHIVO ***"))
        for p in pendientes:
            lineas.append(_comentario(pp, f"***   - {p} - buscar esta operacion mas abajo para ver el motivo"))
        lineas.append(_comentario(pp, "*** ESTAS OPERACIONES NO ESTAN EN EL SOLIDO NI EN ESTE CODIGO - NO ASUMIR QUE SI ***"))
        lineas.append(_comentario(pp, "*" * 60))
    lineas.append(_comentario(pp, f"Pieza: {pieza.pieza} | Material: {pieza.material.nombre} | Cantidad: {pieza.cantidad}"))
    lineas.append(_comentario(pp, f"Postprocesador: {pp['nombre_display']}"))
    lineas.append(_comentario(pp, f"Generado: {datetime.now(timezone.utc).isoformat()}"))
    lineas.append("")
    lineas.append(f"{pp['numero_programa_prefijo']}{numero_programa}")
    lineas.append("G90 G54 G17 G40 G49 G80")
    lineas.append(pp["comando_unidades_mm"] if pieza.unidades == "mm" else pp["comando_unidades_pulg"])
    lineas.append(f"G0 Z{pp['plano_seguridad_mm']:.3f}")
    lineas.append("")
    lineas.extend(lineas_operaciones)
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
