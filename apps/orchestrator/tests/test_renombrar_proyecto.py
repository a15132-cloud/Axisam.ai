"""PUT /api/projects/{id}/nombre - lets a user rename a project so multiple
projects in the sidebar don't get confused with each other (they all start
with the same auto-generated "Pieza <fecha> <hora>" name otherwise).
"""

from __future__ import annotations

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

    return TestClient(app)


def test_renombrar_proyecto_actualiza_nombre(client):
    creado = client.post("/api/projects", json={"nombre": "Pieza 08/08/2026 10:00"})
    project_id = creado.json()["id"]

    resp = client.put(f"/api/projects/{project_id}/nombre", json={"nombre": "Placa de montaje PM-001"})

    assert resp.status_code == 200
    assert resp.json()["nombre"] == "Placa de montaje PM-001"

    releido = client.get(f"/api/projects/{project_id}")
    assert releido.json()["nombre"] == "Placa de montaje PM-001"


def test_renombrar_proyecto_recorta_espacios(client):
    creado = client.post("/api/projects", json={"nombre": "original"})
    project_id = creado.json()["id"]

    resp = client.put(f"/api/projects/{project_id}/nombre", json={"nombre": "  Con espacios  "})

    assert resp.status_code == 200
    assert resp.json()["nombre"] == "Con espacios"


def test_renombrar_proyecto_vacio_falla(client):
    creado = client.post("/api/projects", json={"nombre": "original"})
    project_id = creado.json()["id"]

    resp = client.put(f"/api/projects/{project_id}/nombre", json={"nombre": "   "})

    assert resp.status_code == 422


def test_renombrar_proyecto_inexistente_404(client):
    resp = client.put("/api/projects/AXC-NOEXISTE/nombre", json={"nombre": "algo"})
    assert resp.status_code == 404
