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


def diagnostico_almacenamiento() -> dict:
    """Answers "is this actually a persistent disk, or just a directory
    inside the container's own throwaway filesystem?" with hard evidence
    instead of a guess - exposed via /api/health so this can be confirmed
    from a browser/curl without shell access to the deployment.

    The check: a real mounted volume (Render's persistent disk, an EBS
    volume, etc.) is a SEPARATE filesystem from its parent directory, which
    means the OS assigns it a different device id (st_dev) - directories
    that are just regular folders on the same filesystem always share their
    parent's st_dev. This is the same signal `mountpoint(1)` uses on Linux,
    here without shelling out. It can't detect every deployment shape (e.g.
    a persistent disk mounted at "/", or non-Render hosts), but it reliably
    tells apart the one scenario this project's users keep hitting: Render's
    "Free" plan silently giving `storage_dir` a normal, wiped-on-every-restart
    directory instead of the persistent disk render.yaml asks for.

    "Not a separate mount point" is ONLY a real problem on a deployment that
    actually expects an ephemeral container filesystem to be backed by a
    persistent volume (Render et al - see `settings.storage_dir_debe_ser_persistente`,
    only ever set true by render.yaml). On the desktop app (apps/desktop) or
    plain local dev, `storage_dir` is a perfectly normal, permanently-on-disk
    folder in the user's own filesystem - it will never be a separate mount
    point, and that is completely fine, not a warning sign. Surfacing the
    Render-flavored advertencia there anyway was a real bug (a desktop user
    who never touched Render would see "confirma que el plan sea Starter en
    Render" for a condition that isn't a problem at all) - gate it on the
    same flag routes_projects.py already uses to decide whether a missing
    mount point means anything.
    """
    base = _base_dir()
    try:
        dev_base = base.stat().st_dev
        dev_padre = base.parent.stat().st_dev
        es_punto_de_montaje = dev_base != dev_padre
    except OSError:
        return {
            "ruta": str(base),
            "es_punto_de_montaje": None,
            "advertencia": "No se pudo verificar si el almacenamiento es persistente (error de sistema de archivos).",
        }
    if es_punto_de_montaje or not settings.storage_dir_debe_ser_persistente:
        return {"ruta": str(base), "es_punto_de_montaje": es_punto_de_montaje, "advertencia": None}
    return {
        "ruta": str(base),
        "es_punto_de_montaje": False,
        "advertencia": (
            f"'{base}' NO es un punto de montaje separado - es una carpeta normal dentro del sistema de "
            "archivos temporal del contenedor. Los proyectos guardados aqui se BORRAN en cada redeploy o "
            "reinicio. En Render esto pasa cuando el servicio esta en el plan 'Free' (no soporta discos "
            "persistentes) en vez de 'Starter' o superior - ver el bloque `disk:` en render.yaml."
        ),
    }


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


def guardar_bytes(project_id: str, nombre: str, contenido: bytes) -> Path:
    ruta = _archivos_dir(project_id) / nombre
    ruta.write_bytes(contenido)
    return ruta


def ruta_plano_subido(project_id: str, nombre: str) -> Path:
    d = _proyectos_dir() / project_id / "plano"
    d.mkdir(parents=True, exist_ok=True)
    return d / nombre


def guardar_plano_subido(project_id: str, nombre: str, contenido: bytes) -> Path:
    ruta = ruta_plano_subido(project_id, nombre)
    ruta.write_bytes(contenido)
    return ruta
