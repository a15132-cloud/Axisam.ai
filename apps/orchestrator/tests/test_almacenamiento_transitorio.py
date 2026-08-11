"""A project that genuinely doesn't exist and one this instance can't see
right now because its persistent disk hasn't finished (re)attaching after a
deploy both raise the exact same FileNotFoundError in storage.cargar_proyecto
- see _obtener_o_404 in app/api/routes_projects.py. This was caught live: a
real user's project 404'd immediately after a successful confirm-extraccion
call, right around when a backend deploy had just gone out - a transient
storage reconnect masquerading as "your project is gone forever".

storage_dir_debe_ser_persistente (AXISCAM_STORAGE_PERSISTENTE in render.yaml)
gates this - it must be explicitly true (only set in production) before a
"not currently a mount point" reading is treated as transient. Without that
gate, every 404 in local dev/tests (where storage_dir is just a plain tmp_path
by design, never meant to be a real mount) would incorrectly turn into a 503.
"""

from __future__ import annotations

import dataclasses
import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AXISCAM_STORAGE_DIR", str(tmp_path))

    import app.storage.files as storage_module

    importlib.reload(storage_module)

    import app.api.routes_projects as routes_projects_module

    monkeypatch.setattr(routes_projects_module, "storage", storage_module)

    from app.main import app

    return TestClient(app), routes_projects_module


def test_404_normal_cuando_no_se_espera_disco_persistente(client):
    """Default (flag off, as in every local/test run): a missing project is
    still a plain 404, never masked as a transient error."""
    test_client, _ = client
    resp = test_client.get("/api/projects/AXC-NOEXISTE")
    assert resp.status_code == 404
    assert "no encontrado" in resp.json()["detail"]


def test_503_cuando_se_espera_disco_persistente_y_no_esta_montado(client):
    """Flag on (as render.yaml sets in production) + storage_dir not
    actually a separate mount (exactly what tmp_path looks like, and exactly
    what a fresh container looks like before its disk finishes attaching):
    the same missing-project condition must come back as a retryable 503,
    not a 404 that reads as permanent data loss.
    """
    test_client, routes_projects_module = client
    monkeypatch_settings = dataclasses.replace(routes_projects_module.settings, storage_dir_debe_ser_persistente=True)
    routes_projects_module.settings = monkeypatch_settings

    try:
        resp = test_client.get("/api/projects/AXC-NOEXISTE")
        assert resp.status_code == 503
        assert "no se perdio" in resp.json()["detail"] or "no se perdió" in resp.json()["detail"]
    finally:
        routes_projects_module.settings = dataclasses.replace(monkeypatch_settings, storage_dir_debe_ser_persistente=False)


def test_503_no_oculta_un_proyecto_que_si_existe(client):
    """The 503 path only kicks in on a genuine lookup failure - a project
    that's actually on disk must never be affected by this flag."""
    test_client, routes_projects_module = client
    monkeypatch_settings = dataclasses.replace(routes_projects_module.settings, storage_dir_debe_ser_persistente=True)
    routes_projects_module.settings = monkeypatch_settings

    try:
        creado = test_client.post("/api/projects", json={"nombre": "existe de verdad"})
        project_id = creado.json()["id"]

        resp = test_client.get(f"/api/projects/{project_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == project_id
    finally:
        routes_projects_module.settings = dataclasses.replace(monkeypatch_settings, storage_dir_debe_ser_persistente=False)
