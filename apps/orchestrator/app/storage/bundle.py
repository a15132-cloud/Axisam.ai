"""Builds the "download everything" ZIP for a project: every generated
artifact (STEP/STL/G-code) plus a plain-text summary report, so a shop
user gets one file with everything needed to pick up the part in
SolidWorks/Mastercam and see exactly what the agent did and didn't
verify - instead of hunting for individual download buttons.
"""

from __future__ import annotations

import io
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from app.schemas.project import Proyecto


def _linea_separadora() -> str:
    return "=" * 70


def generar_resumen_texto(proyecto: Proyecto) -> str:
    partes: list[str] = []
    partes.append(_linea_separadora())
    partes.append(f"AXISCAM - Resumen del proyecto {proyecto.id}")
    partes.append(_linea_separadora())
    partes.append(f"Nombre: {proyecto.nombre}")
    partes.append(f"Etapa actual: {proyecto.etapa.value}")
    partes.append(f"Generado: {datetime.now(timezone.utc).isoformat()}")
    partes.append("")

    if proyecto.pieza_extraida:
        pz = proyecto.pieza_extraida
        d = pz.dimensiones
        partes.append("--- PIEZA ---")
        partes.append(f"Nombre: {pz.pieza}")
        partes.append(f"Material: {pz.material.nombre}")
        partes.append(f"Cantidad: {pz.cantidad}")
        partes.append(f"Tolerancia general: +/-{pz.tolerancia_general.valor_mm} mm ({pz.tolerancia_general.norma})")
        partes.append(f"Acabado superficial: {pz.acabado_superficial or 'N/A'}")
        if d.forma_base.value == "rectangular":
            partes.append(f"Dimensiones: {d.largo_mm} x {d.ancho_mm} x {d.espesor_mm} mm (LxAxE)")
        else:
            partes.append(f"Dimensiones: Ø{d.diametro_mm} x {d.espesor_mm} mm")
        partes.append(f"Confianza de extraccion: {pz.extraccion.confianza_global:.0%}")
        if pz.extraccion.campos_baja_confianza:
            partes.append(f"Campos de baja confianza: {', '.join(pz.extraccion.campos_baja_confianza)}")
        partes.append("")
        partes.append(f"Features ({len(pz.features)}):")
        for i, f in enumerate(pz.features, start=1):
            medida = f"Ø{f.diametro_mm}mm" if f.diametro_mm else (f"R{f.radio_mm}mm" if f.radio_mm else "")
            partes.append(f"  {i}. {f.tipo.value} {medida}".rstrip())
        partes.append("")

    if proyecto.toolpath_plan:
        plan = proyecto.toolpath_plan
        partes.append("--- PLAN DE TRAYECTORIAS (Capa 5, base de reglas) ---")
        partes.append(f"Postprocesador: {proyecto.postprocesador or 'default'}")
        if plan.tiempo_estimado_min is not None:
            partes.append(f"Tiempo estimado: ~{plan.tiempo_estimado_min} min")
        for op in plan.operaciones:
            partes.append(f"  - [{op.get('feature_id', '?')}] {op.get('estrategia')} | {op.get('herramienta')} | {op.get('rpm')} RPM, {op.get('avance_mm_min')} mm/min")
        if plan.advertencias:
            partes.append("Advertencias:")
            for w in plan.advertencias:
                partes.append(f"  ! {w}")
        partes.append("")

    if proyecto.simulacion:
        partes.append("--- SIMULACION DE MAQUINADO (estimada, no verificada por Mastercam real) ---")
        partes.append(f"Tiempo estimado: {proyecto.simulacion.get('tiempo_estimado_min')} min")
        partes.append(f"Operaciones: {proyecto.simulacion.get('numero_operaciones')}")
        partes.append(f"Cambios de herramienta: {proyecto.simulacion.get('cambios_herramienta')}")
        partes.append("")

    partes.append("--- APROBACION ---")
    partes.append(f"Aprobado: {'si' if proyecto.aprobacion_final else 'no'}")
    if proyecto.aprobacion_final:
        partes.append(f"Aprobado por: {proyecto.aprobado_por}")
        partes.append(f"Aprobado en: {proyecto.aprobado_en}")
    partes.append("")

    partes.append("--- ARCHIVOS INCLUIDOS ---")
    for a in proyecto.archivos:
        etiqueta = " (SIMULACION - verificar con Mastercam real antes de usar)" if a.es_simulacion else " (geometria real)"
        partes.append(f"  - {a.nombre} [{a.tipo}]{etiqueta}")
    partes.append("")

    partes.append(_linea_separadora())
    partes.append("AVISO IMPORTANTE")
    partes.append(_linea_separadora())
    tiene_gcode = any(a.tipo == "gcode" for a in proyecto.archivos)
    if tiene_gcode:
        # Axiscam's normal flow never produces a gcode archivo (see
        # app/agent/approval.py's module docstring: the product is CAD-only,
        # confirmar_modelo is the last checkpoint) - this branch only fires
        # for a project whose files were populated directly through the
        # retained-but-unreachable CAM engine (app/cam/*.py), e.g. in a test
        # or a manual script. Keep the honest disclaimer for that case
        # rather than assume it can never happen.
        partes.append(
            "El modelo 3D (STEP/STL) se genero con un motor de geometria real (OpenCascade) a partir\n"
            "de las medidas confirmadas - es geometria real, utilizable en SolidWorks/Mastercam.\n\n"
            "Este proyecto tambien incluye un archivo de codigo G: sigue siendo una SIMULACION basada\n"
            "en reglas (el motor CAM de Axiscam, app/cam/*.py) - tiene trayectoria real para taladrado,\n"
            "cajeras/ranuras y contornos, pero NO ha sido verificada por Mastercam real (sin chequeo de\n"
            "colisiones/gubias entre features simultaneos). Un maquinista debe revisar el archivo\n"
            "completo antes de cargarlo en la maquina CNC."
        )
    else:
        partes.append(
            "El modelo 3D (STEP/STL) se genero con un motor de geometria real (OpenCascade) a partir\n"
            "de las medidas confirmadas - es geometria real, utilizable en SolidWorks/Mastercam.\n\n"
            "Axiscam es una herramienta de CAD: entrega el modelo 3D, no trayectorias de maquinado ni\n"
            "codigo G. Un programador CAM/maquinista debe programar el maquinado de esta pieza en\n"
            "Mastercam (u otro CAM) a partir de este STEP."
        )
    return "\n".join(partes)


def generar_zip(proyecto: Proyecto) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("RESUMEN.txt", generar_resumen_texto(proyecto))
        for archivo in proyecto.archivos:
            ruta = Path(archivo.ruta)
            if ruta.exists():
                zf.write(ruta, arcname=archivo.nombre)
    buffer.seek(0)
    return buffer.getvalue()
