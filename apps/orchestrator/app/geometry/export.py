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
