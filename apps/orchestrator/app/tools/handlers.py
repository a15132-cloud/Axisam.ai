"""Capa 4 dispatch: the actual work behind each tool the agent can call.

Every function re-checks its precondition against `proyecto.etapa` /
confirmation flags even though the system prompt also tells Claude the
same rules. Never rely on the model alone to enforce a safety gate -
enforce it here too, so a confused or adversarially-prompted turn can't
skip a checkpoint just by calling a tool out of order.
"""

from __future__ import annotations

import base64

from app.cam.gcode import generar_codigo_g as _generar_codigo_g
from app.cam.planner import planear_trayectoria
from app.cam.simulate import simular_maquinado as _simular_maquinado
from app.geometry.builder import GeometryBuildError, build_pieza
from app.geometry.export import calcular_propiedades, exportar_step, exportar_stl
from app.integrations import windows_bridge
from app.schemas.project import ArchivoGenerado, Etapa, Proyecto
from app.storage import files as storage


class PrecondicionNoCumplida(Exception):
    """A tool was invoked before its required human checkpoint passed."""


def generar_modelo_3d(proyecto: Proyecto) -> dict:
    if not proyecto.pieza_confirmada or proyecto.pieza_extraida is None:
        raise PrecondicionNoCumplida(
            "El usuario debe confirmar los datos extraidos del plano (Capa 6, checkpoint 1) "
            "antes de generar el modelo 3D."
        )

    proyecto.etapa = Etapa.MODELANDO

    # Prefer the user's own real SolidWorks over the simulated engine
    # whenever apps/windows-bridge is reachable and reports it available -
    # see app/integrations/windows_bridge.py for the "conecta facil"
    # contract. A genuine failure here (bridge reachable, SolidWorks call
    # attempted, call failed) must reach the user, not be hidden behind a
    # silent fallback to a simulated result.
    try:
        resultado_bridge = windows_bridge.generar_modelo_solidworks(proyecto.pieza_extraida)
    except windows_bridge.BridgeError as exc:
        proyecto.etapa = Etapa.ERROR
        proyecto.registrar_evento("Error generando modelo 3D en SolidWorks real", detalle=str(exc))
        raise

    if resultado_bridge is not None:
        return _guardar_modelo_desde_bridge(proyecto, resultado_bridge)

    try:
        resultado = build_pieza(proyecto.pieza_extraida)
    except GeometryBuildError as exc:
        proyecto.etapa = Etapa.ERROR
        proyecto.registrar_evento("Error generando modelo 3D", detalle=str(exc))
        raise

    props = calcular_propiedades(resultado.solido)
    nombre_base = proyecto.pieza_extraida.pieza or "pieza"
    step_path = storage.ruta_archivo_generado(proyecto.id, f"{nombre_base}.step")
    stl_path = storage.ruta_archivo_generado(proyecto.id, f"{nombre_base}.stl")
    exportar_step(resultado.solido, step_path)
    exportar_stl(resultado.solido, stl_path)

    proyecto.archivos.append(ArchivoGenerado(nombre=step_path.name, tipo="step", ruta=str(step_path), es_simulacion=True))
    proyecto.archivos.append(ArchivoGenerado(nombre=stl_path.name, tipo="stl", ruta=str(stl_path), es_simulacion=True))
    proyecto.advertencias_modelo = resultado.advertencias
    proyecto.features_omitidos_modelo = resultado.features_omitidos
    proyecto.etapa = Etapa.ESPERANDO_CONFIRMACION_MODELO
    proyecto.registrar_evento(
        "Modelo 3D generado (motor simulado)",
        detalle=f"{len(resultado.advertencias)} advertencia(s), {len(resultado.features_omitidos)} feature(s) omitidos",
    )

    return {
        "propiedades_geometricas": props,
        "advertencias": resultado.advertencias,
        "features_omitidos": resultado.features_omitidos,
        "archivos_generados": [step_path.name, stl_path.name],
        "generado_con": "simulado",
    }


def _guardar_modelo_desde_bridge(proyecto: Proyecto, data: dict) -> dict:
    nombre_base = data.get("nombre_archivo") or (proyecto.pieza_extraida.pieza if proyecto.pieza_extraida else "pieza")
    step_path = storage.guardar_bytes(proyecto.id, f"{nombre_base}.step", base64.b64decode(data["archivo_step_base64"]))
    stl_path = storage.guardar_bytes(proyecto.id, f"{nombre_base}.stl", base64.b64decode(data["archivo_stl_base64"]))

    advertencias = data.get("advertencias", [])
    features_omitidos = data.get("features_omitidos", [])
    props = data.get("propiedades_geometricas") or {}

    proyecto.archivos.append(ArchivoGenerado(nombre=step_path.name, tipo="step", ruta=str(step_path), es_simulacion=False))
    proyecto.archivos.append(ArchivoGenerado(nombre=stl_path.name, tipo="stl", ruta=str(stl_path), es_simulacion=False))
    proyecto.advertencias_modelo = advertencias
    proyecto.features_omitidos_modelo = features_omitidos
    proyecto.etapa = Etapa.ESPERANDO_CONFIRMACION_MODELO
    proyecto.registrar_evento(
        "Modelo 3D generado con SolidWorks real",
        detalle=f"{len(advertencias)} advertencia(s), {len(features_omitidos)} feature(s) omitidos",
    )

    return {
        "propiedades_geometricas": props,
        "advertencias": advertencias,
        "features_omitidos": features_omitidos,
        "archivos_generados": [step_path.name, stl_path.name],
        "generado_con": "solidworks_real",
    }


def generar_trayectorias(proyecto: Proyecto, postprocesador: str | None = None) -> dict:
    if not proyecto.modelo_confirmado or proyecto.pieza_extraida is None:
        raise PrecondicionNoCumplida(
            "El usuario debe confirmar el modelo 3D (Capa 6, checkpoint 2) antes de generar trayectorias."
        )

    proyecto.etapa = Etapa.GENERANDO_TRAYECTORIAS
    proyecto.postprocesador = postprocesador or proyecto.postprocesador
    plan_detallado = planear_trayectoria(proyecto.pieza_extraida, proyecto.postprocesador)
    proyecto.toolpath_plan = plan_detallado.plan
    proyecto.registrar_evento("Trayectorias planeadas", detalle=plan_detallado.plan.estrategia)

    return {
        "plan": plan_detallado.plan.model_dump(),
        "postprocesador": plan_detallado.postprocesador["nombre_display"],
    }


def simular_maquinado(proyecto: Proyecto) -> dict:
    if proyecto.toolpath_plan is None or proyecto.pieza_extraida is None:
        raise PrecondicionNoCumplida("Debes generar las trayectorias antes de simular el maquinado.")

    proyecto.etapa = Etapa.SIMULANDO
    plan_detallado = planear_trayectoria(proyecto.pieza_extraida, proyecto.postprocesador)
    resumen = _simular_maquinado(proyecto.pieza_extraida, plan_detallado)

    proyecto.simulacion = {
        "tiempo_estimado_min": resumen.tiempo_estimado_min,
        "numero_operaciones": resumen.numero_operaciones,
        "numero_herramientas": resumen.numero_herramientas,
        "herramientas": resumen.herramientas,
        "cambios_herramienta": resumen.cambios_herramienta,
        "advertencias": resumen.advertencias,
        "es_simulacion": resumen.es_simulacion,
    }
    proyecto.etapa = Etapa.ESPERANDO_APROBACION_FINAL
    proyecto.registrar_evento(
        "Simulacion de maquinado generada",
        detalle=f"~{resumen.tiempo_estimado_min} min estimados, {resumen.numero_herramientas} herramienta(s)",
    )

    return proyecto.simulacion


def exportar_codigo_g(proyecto: Proyecto) -> dict:
    if not proyecto.aprobacion_final or proyecto.pieza_extraida is None:
        raise PrecondicionNoCumplida(
            "El usuario debe dar la aprobacion final (Capa 6, checkpoint 3, despues de revisar la "
            "simulacion) antes de exportar codigo G."
        )

    plan_detallado = planear_trayectoria(proyecto.pieza_extraida, proyecto.postprocesador)

    # Same "prefer real hardware when reachable" contract as generar_modelo_3d.
    try:
        resultado_bridge = windows_bridge.generar_codigo_g_mastercam(
            proyecto.pieza_extraida, plan_detallado.plan, proyecto.postprocesador or "haas_vf_generico"
        )
    except windows_bridge.BridgeError as exc:
        proyecto.registrar_evento("Error exportando codigo G en Mastercam real", detalle=str(exc))
        raise

    nombre_base = proyecto.pieza_extraida.pieza or "pieza"
    ext = plan_detallado.postprocesador["extension_archivo"]

    if resultado_bridge is not None:
        ruta = storage.guardar_texto(proyecto.id, f"{nombre_base}{ext}", resultado_bridge["contenido"])
        proyecto.archivos.append(ArchivoGenerado(nombre=ruta.name, tipo="gcode", ruta=str(ruta), es_simulacion=False))
        proyecto.codigo_g_resumen = {
            "archivo": ruta.name,
            "operaciones_con_movimiento_real": resultado_bridge.get("operaciones_con_movimiento_real", 0),
            "operaciones_solo_planeadas": resultado_bridge.get("operaciones_solo_planeadas", 0),
            "advertencias": resultado_bridge.get("advertencias", []),
        }
        proyecto.registrar_evento("Codigo G exportado con Mastercam real")
        return {**proyecto.codigo_g_resumen, "es_simulacion": False}

    resultado = _generar_codigo_g(proyecto.pieza_extraida, plan_detallado)
    ruta = storage.guardar_texto(proyecto.id, f"{nombre_base}{ext}", resultado.contenido)
    proyecto.archivos.append(ArchivoGenerado(nombre=ruta.name, tipo="gcode", ruta=str(ruta), es_simulacion=True))
    proyecto.codigo_g_resumen = {
        "archivo": ruta.name,
        "operaciones_con_movimiento_real": resultado.operaciones_con_movimiento_real,
        "operaciones_solo_planeadas": resultado.operaciones_solo_planeadas,
        "advertencias": resultado.advertencias,
    }
    proyecto.registrar_evento(
        "Codigo G exportado (simulacion)",
        detalle=f"{resultado.operaciones_con_movimiento_real} operacion(es) con trayectoria real, "
        f"{resultado.operaciones_solo_planeadas} solo planeadas",
    )

    return {**proyecto.codigo_g_resumen, "es_simulacion": True}
