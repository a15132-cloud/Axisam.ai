"""Download endpoints for generated artifacts (STEP/STL/G-code).

Deliberately validates the requested filename against the project's own
`archivos` list rather than serving `storage_dir` as a static mount -
that list is the only thing that says a given file actually belongs to
this project, so a raw static mount would let one project's URL guess
its way into another's files.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response

from app.storage import bundle, files as storage

router = APIRouter(prefix="/api/projects", tags=["files"])

_MEDIA_TYPES = {
    "step": "application/step",
    "stl": "model/stl",
    "gcode": "text/plain",
}


@router.get("/{project_id}/files/{nombre_archivo}")
def descargar_archivo(project_id: str, nombre_archivo: str) -> FileResponse:
    try:
        proyecto = storage.cargar_proyecto(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    archivo = next((a for a in proyecto.archivos if a.nombre == nombre_archivo), None)
    if archivo is None:
        raise HTTPException(status_code=404, detail=f"'{nombre_archivo}' no pertenece a este proyecto")

    ruta = Path(archivo.ruta)
    if not ruta.exists():
        raise HTTPException(status_code=410, detail=f"El archivo '{nombre_archivo}' ya no esta disponible en el servidor")

    return FileResponse(
        path=ruta,
        filename=archivo.nombre,
        media_type=_MEDIA_TYPES.get(archivo.tipo, "application/octet-stream"),
    )


@router.get("/{project_id}/descargar-todo")
def descargar_todo(project_id: str) -> Response:
    try:
        proyecto = storage.cargar_proyecto(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if not proyecto.archivos:
        raise HTTPException(status_code=404, detail="Este proyecto todavia no tiene archivos generados")

    contenido = bundle.generar_zip(proyecto)
    nombre_pieza = proyecto.pieza_extraida.pieza if proyecto.pieza_extraida else proyecto.id
    nombre_archivo = f"{nombre_pieza}_axiscam.zip"
    return Response(
        content=contenido,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{nombre_archivo}"'},
    )


@router.get("/{project_id}/plano-original")
def descargar_plano_original(project_id: str) -> FileResponse:
    try:
        proyecto = storage.cargar_proyecto(project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if not proyecto.archivo_plano:
        raise HTTPException(status_code=404, detail="Este proyecto no tiene un plano subido")

    ruta = storage.ruta_plano_subido(project_id, proyecto.archivo_plano)
    if not ruta.exists():
        raise HTTPException(status_code=410, detail="El plano original ya no esta disponible en el servidor")

    return FileResponse(path=ruta, filename=proyecto.archivo_plano)
