"""Local filesystem persistence: one JSON file per project, one folder
per project for generated artifacts. No database - a real shop doing a
few dozen parts a day doesn't need one yet, and a flat JSON-per-project
store is trivial to inspect/back up/migrate later.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from app.config import settings
from app.schemas.project import Proyecto


def _base_dir() -> Path:
    p = Path(settings.storage_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _proyectos_dir() -> Path:
    d = _base_dir() / "projects"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _proyecto_json_path(project_id: str) -> Path:
    return _proyectos_dir() / f"{project_id}.json"


def _archivos_dir(project_id: str) -> Path:
    d = _proyectos_dir() / project_id / "files"
    d.mkdir(parents=True, exist_ok=True)
    return d


def guardar_proyecto(proyecto: Proyecto) -> None:
    _proyecto_json_path(proyecto.id).write_text(proyecto.model_dump_json(indent=2), encoding="utf-8")


def cargar_proyecto(project_id: str) -> Proyecto:
    ruta = _proyecto_json_path(project_id)
    if not ruta.exists():
        raise FileNotFoundError(f"Proyecto '{project_id}' no encontrado")
    return Proyecto.model_validate_json(ruta.read_text(encoding="utf-8"))


def listar_proyectos() -> list[Proyecto]:
    archivos = sorted(_proyectos_dir().glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    return [Proyecto.model_validate_json(f.read_text(encoding="utf-8")) for f in archivos]


def eliminar_proyecto(project_id: str) -> None:
    ruta = _proyecto_json_path(project_id)
    if ruta.exists():
        ruta.unlink()
    carpeta = _proyectos_dir() / project_id
    if carpeta.exists():
        shutil.rmtree(carpeta)


def ruta_archivo_generado(project_id: str, nombre: str) -> Path:
    """Reserves a path under the project's files/ dir. Callers write the
    actual bytes (cadquery exporters write directly to a path)."""
    return _archivos_dir(project_id) / nombre


def guardar_texto(project_id: str, nombre: str, contenido: str) -> Path:
    ruta = _archivos_dir(project_id) / nombre
    ruta.write_text(contenido, encoding="utf-8")
    return ruta


def ruta_plano_subido(project_id: str, nombre: str) -> Path:
    d = _proyectos_dir() / project_id / "plano"
    d.mkdir(parents=True, exist_ok=True)
    return d / nombre


def guardar_plano_subido(project_id: str, nombre: str, contenido: bytes) -> Path:
    ruta = ruta_plano_subido(project_id, nombre)
    ruta.write_bytes(contenido)
    return ruta
