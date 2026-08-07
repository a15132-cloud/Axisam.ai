"""Capa 4 dispatch: the actual work behind each tool the agent can call.

Every function re-checks its precondition against `proyecto.etapa` /
confirmation flags even though the system prompt also tells Claude the
same rules. Never rely on the model alone to enforce a safety gate -
enforce it here too, so a confused or adversarially-prompted turn can't
skip a checkpoint just by calling a tool out of order.
"""

from __future__ import annotations

from app.cam.gcode import generar_codigo_g as _generar_codigo_g
from app.cam.planner import planear_trayectoria
from app.cam.simulate import simular_maquinado as _simular_maquinado
from app.geometry.builder import GeometryBuildError, build_pieza
from app.geometry.export import calcular_propiedades, exportar_step, exportar_stl
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

    proyecto.archivos.append(ArchivoGenerado(nombre=step_path.name, tipo="step", ruta=str(step_path), es_simulacion=False))
    proyecto.archivos.append(ArchivoGenerado(nombre=stl_path.name, tipo="stl", ruta=str(stl_path), es_simulacion=False))
    proyecto.advertencias_modelo = resultado.advertencias
    proyecto.features_omitidos_modelo = resultado.features_omitidos
    proyecto.etapa = Etapa.ESPERANDO_CONFIRMACION_MODELO
    proyecto.registrar_evento(
        "Modelo 3D generado",
        detalle=f"{len(resultado.advertencias)} advertencia(s), {len(resultado.features_omitidos)} feature(s) omitidos",
    )

    return {
        "propiedades_geometricas": props,
        "advertencias": resultado.advertencias,
        "features_omitidos": resultado.features_omitidos,
        "archivos_generados": [step_path.name, stl_path.name],
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
    resultado = _generar_codigo_g(proyecto.pieza_extraida, plan_detallado)

    nombre_base = proyecto.pieza_extraida.pieza or "pieza"
    ext = plan_detallado.postprocesador["extension_archivo"]
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
