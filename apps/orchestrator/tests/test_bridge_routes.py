"""POST /api/projects/{id}/activar-solidworks and /abrir-mastercam - the
"Ver en SolidWorks" / "Abrir en Mastercam" buttons in the chat. Both proxy
to the local Windows bridge (app.integrations.windows_bridge), which is
never actually reachable in this test environment - so these tests cover
the gating logic (no model yet / model was simulated, not real) that runs
BEFORE the bridge is ever contacted, plus the "bridge unreachable" 502
that's the honest, unmocked default everywhere except the user's own
Windows shop-floor PC.
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


def _crear_proyecto(client) -> str:
    return client.post("/api/projects", json={"nombre": "Placa PM-001"}).json()["id"]


def _agregar_archivo_step(client, project_id: str, *, es_simulacion: bool) -> None:
    import app.storage.files as storage
    from app.schemas.project import ArchivoGenerado

    proyecto = storage.cargar_proyecto(project_id)
    ruta = storage.ruta_archivo_generado(project_id, "placa.step")
    ruta.write_bytes(b"ISO-10303-21;")
    proyecto.archivos.append(ArchivoGenerado(nombre="placa.step", tipo="step", ruta=str(ruta), es_simulacion=es_simulacion))
    storage.guardar_proyecto(proyecto)


def test_activar_solidworks_404_si_no_existe_proyecto(client):
    resp = client.post("/api/projects/AXC-NOEXISTE/activar-solidworks")
    assert resp.status_code == 404


def test_activar_solidworks_409_sin_modelo_generado(client):
    project_id = _crear_proyecto(client)
    resp = client.post(f"/api/projects/{project_id}/activar-solidworks")
    assert resp.status_code == 409
    assert "modelo 3d generado" in resp.json()["detail"].lower()


def test_activar_solidworks_409_cuando_modelo_es_simulado(client):
    project_id = _crear_proyecto(client)
    _agregar_archivo_step(client, project_id, es_simulacion=True)

    resp = client.post(f"/api/projects/{project_id}/activar-solidworks")

    assert resp.status_code == 409
    assert "motor simulado" in resp.json()["detail"].lower()


def test_activar_solidworks_502_cuando_bridge_no_alcanzable(client):
    project_id = _crear_proyecto(client)
    _agregar_archivo_step(client, project_id, es_simulacion=False)

    # No bridge listens on 127.0.0.1:5757 in this test environment - the
    # real, unmocked failure mode for every machine except the user's own
    # Windows shop-floor PC (same pattern as test_windows_bridge.py).
    resp = client.post(f"/api/projects/{project_id}/activar-solidworks")

    assert resp.status_code == 502


def test_abrir_mastercam_404_si_no_existe_proyecto(client):
    resp = client.post("/api/projects/AXC-NOEXISTE/abrir-mastercam")
    assert resp.status_code == 404


def test_abrir_mastercam_409_sin_step_generado(client):
    project_id = _crear_proyecto(client)
    resp = client.post(f"/api/projects/{project_id}/abrir-mastercam")
    assert resp.status_code == 409


def test_abrir_mastercam_502_cuando_bridge_no_alcanzable_incluso_si_es_simulado(client):
    # Unlike activar-solidworks, abrir-mastercam doesn't care whether the
    # model was simulated - Mastercam never automated anything either way,
    # this is just "open the app with the file" (see MastercamService).
    project_id = _crear_proyecto(client)
    _agregar_archivo_step(client, project_id, es_simulacion=True)

    resp = client.post(f"/api/projects/{project_id}/abrir-mastercam")

    assert resp.status_code == 502
