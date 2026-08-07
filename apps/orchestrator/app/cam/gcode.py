"""Capa 4 (Mastercam side) - `exportar_codigo_g_mastercam`.

Turns a PlanDetallado into an actual .nc file. Two honesty rules drive
every decision here, straight from the project brief:

1. Never let fabricated toolpath motion look authoritative. Drilling with
   canned cycles is simple, well-defined geometry (position + depth) - we
   generate it for real. Pocket clearing, contour offsetting, multi-axis
   moves need an actual CAM engine (gouge checking, linking moves) that
   this codebase does not implement - those get an explicit comment
   placeholder, never invented G1/G2/G3 motion.
2. Every file this function produces is stamped, top and bottom, as a
   simulation pending real Mastercam SDK integration. Capa 6 still
   requires human approval regardless, but the file itself must not be
   mistakable for verified, machine-ready code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.cam.planner import PlanDetallado
from app.schemas.piece import Feature, Pieza, TipoFeature

DISCLAIMER = (
    "*** SIMULACION - NO VERIFICADO POR MASTERCAM REAL ***\n"
    "*** NO CARGAR EN LA MAQUINA CNC SIN REVISION DE UN MAQUINISTA ***\n"
    "*** Generado por el motor de reglas de Axiscam (Capa 5), pendiente integracion con Mastercam SDK ***"
)

FEATURES_CON_CICLO_REAL = {TipoFeature.BARRENO, TipoFeature.BARRENO_ROSCADO}


@dataclass
class ResultadoGCode:
    contenido: str
    operaciones_con_movimiento_real: int = 0
    operaciones_solo_planeadas: int = 0
    advertencias: list[str] = field(default_factory=list)


def _comentario(pp: dict, texto: str) -> str:
    return f"{pp['comentario_apertura']}{texto}{pp['comentario_cierre']}"


def _bloque_taladrado(pp: dict, feature: Feature, op, espesor_pieza: float, tool_num: int) -> list[str]:
    lineas = []
    profundidad = op.profundidad_pasada_mm or espesor_pieza
    z_objetivo = -abs(profundidad)
    ciclo = pp["ciclo_taladrado_profundo"] if profundidad > (op.herramienta.diametro_mm * 3) else pp["ciclo_taladrado_simple"]
    retract = 3.0

    lineas.append(_comentario(pp, f"{feature.tipo.value.upper()} id={feature.id or '?'} - {op.herramienta.descripcion}"))
    lineas.append(pp["cambio_herramienta"].format(tool=tool_num))
    lineas.append(pp["inicio_husillo"].format(rpm=int(op.parametros.rpm)))
    if op.parametros.refrigerante in ("requerido", "recomendado"):
        lineas.append(pp["refrigerante_on"])

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
    if op.parametros.refrigerante in ("requerido", "recomendado"):
        lineas.append(pp["refrigerante_off"])
    lineas.append(f"G0 Z{pp['plano_seguridad_mm']:.3f}")
    return lineas


def _bloque_pendiente(pp: dict, feature: Feature, op) -> list[str]:
    return [
        _comentario(
            pp,
            f"{feature.tipo.value.upper()} id={feature.id or '?'} - ESTRATEGIA: {op.estrategia} - "
            f"HERRAMIENTA SUGERIDA: {op.herramienta.descripcion} - "
            f"RPM~{int(op.parametros.rpm)} F~{op.parametros.avance_mm_min:.0f}mm/min",
        ),
        _comentario(pp, "TRAYECTORIA NO GENERADA - requiere Mastercam real (desbaste/acabado con verificacion anti-colision)"),
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
        if feature.tipo in FEATURES_CON_CICLO_REAL:
            lineas.extend(_bloque_taladrado(pp, feature, op, pieza.dimensiones.espesor_mm, tool_num))
            con_movimiento += 1
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
