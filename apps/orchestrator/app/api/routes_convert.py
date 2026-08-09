"""Stateless file conversion - not tied to any project. Today just
STEP->STL, for the standalone "Simulación" tool: it runs entirely in the
browser and can only draw a triangle mesh, so a STEP file (exact CAD
surfaces, what SolidWorks/Mastercam actually use) needs to be tessellated
into a mesh first. That's a real CAD-kernel operation, not something a
browser can do on its own - this reuses the same OpenCascade engine that
builds Axiscam's own models.
"""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response

from app.geometry.export import convertir_step_a_stl_bytes

router = APIRouter(prefix="/api/convertir", tags=["convertir"])


@router.post("/step-a-stl")
async def step_a_stl(archivo: UploadFile = File(...)) -> Response:
    contenido = await archivo.read()
    if not contenido:
        raise HTTPException(status_code=422, detail="El archivo STEP está vacío.")
    try:
        stl_bytes = convertir_step_a_stl_bytes(contenido)
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail=f"No se pudo leer este archivo como STEP - revisa que sea un .step/.stp válido. Detalle: {exc}",
        ) from exc
    return Response(content=stl_bytes, media_type="model/stl")
