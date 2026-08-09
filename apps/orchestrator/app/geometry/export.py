"""Write a built solid to disk in the formats downstream tools need:
STEP (neutral CAD format SolidWorks/Mastercam import natively) and STL
(lightweight mesh for the in-browser 3D preview).
"""

from __future__ import annotations

from pathlib import Path

import cadquery as cq


def exportar_step(solido: cq.Workplane, ruta: Path) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    cq.exporters.export(solido, str(ruta), exportType="STEP")
    return ruta


def exportar_stl(solido: cq.Workplane, ruta: Path, tolerancia_mm: float = 0.1) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    cq.exporters.export(solido, str(ruta), exportType="STL", tolerance=tolerancia_mm)
    return ruta


def convertir_step_a_stl_bytes(step_bytes: bytes, tolerancia_mm: float = 0.1) -> bytes:
    """Same OpenCascade engine that builds Axiscam's own models, used here
    just as a converter: STEP in, STL bytes out. Exists so the standalone
    "Simulación" tool can accept the same STEP file real CAD/CAM software
    uses, instead of forcing the user to separately track down the STL -
    a browser can only draw a triangle mesh (STL already is one; STEP
    needs a real CAD kernel to tessellate it into one, which is exactly
    what this function does server-side).
    """
    import tempfile

    with tempfile.TemporaryDirectory() as carpeta:
        step_path = Path(carpeta) / "entrada.step"
        stl_path = Path(carpeta) / "salida.stl"
        step_path.write_bytes(step_bytes)
        solido = cq.importers.importStep(str(step_path))
        cq.exporters.export(solido, str(stl_path), exportType="STL", tolerance=tolerancia_mm)
        return stl_path.read_bytes()


def calcular_propiedades(solido: cq.Workplane) -> dict:
    val = solido.val()
    bb = val.BoundingBox()
    return {
        "volumen_mm3": round(val.Volume(), 2),
        "area_superficial_mm2": round(val.Area(), 2),
        "bbox_mm": {
            "x": round(bb.xlen, 3),
            "y": round(bb.ylen, 3),
            "z": round(bb.zlen, 3),
        },
    }
