"""POST /plano and POST /plano/verificar as two separate requests.

Split out from one request that did both Claude passes, after a real
upload against the live deployment showed the combined request landing
right at the edge of the hosting platform's own proxy timeout - a limit
this app has no way to configure around, since it isn't this app's
timeout. See app/vision/extractor.py::extraer_primera_pasada's docstring.
"""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

from app.schemas.piece import Dimensiones, ExtraccionMeta, FormaBase, Material, Pieza
from app.vision.extractor import ResultadoExtraccion


def _pieza_falsa(nombre: str, confianza: float = 0.9) -> Pieza:
    return Pieza(
        pieza=nombre,
        material=Material(nombre="Aluminio 6061"),
        dimensiones=Dimensiones(forma_base=FormaBase.RECTANGULAR, largo_mm=100, ancho_mm=60, espesor_mm=10),
        extraccion=ExtraccionMeta(confianza_global=confianza, campos_baja_confianza=[]),
    )


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AXISCAM_STORAGE_DIR", str(tmp_path))

    import app.storage.files as storage_module

    importlib.reload(storage_module)

    import app.api.routes_projects as routes_projects_module

    monkeypatch.setattr(routes_projects_module, "storage", storage_module)

    from app.main import app

    return TestClient(app)


def _crear_proyecto(client: TestClient) -> str:
    resp = client.post("/api/projects", json={"nombre": "test split"})
    assert resp.status_code == 200
    return resp.json()["id"]


def _subir_plano(client: TestClient, project_id: str) -> dict:
    resp = client.post(
        f"/api/projects/{project_id}/plano",
        files={"archivo": ("plano.pdf", b"%PDF-1.4\n%fake", "application/pdf")},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_subir_plano_solo_hace_la_primera_pasada(client, monkeypatch):
    import app.api.routes_projects as routes_projects_module

    llamadas_verificar = []

    def _primera(*args, **kwargs):
        return ResultadoExtraccion(pieza=_pieza_falsa("pieza_pasada_1"), raw_tool_input={}, stop_reason="tool_use")

    def _segunda(*args, **kwargs):
        llamadas_verificar.append(1)
        raise AssertionError("verificar_segunda_pasada no debe llamarse desde /plano")

    monkeypatch.setattr(routes_projects_module, "extraer_primera_pasada", _primera)
    monkeypatch.setattr(routes_projects_module, "verificar_segunda_pasada", _segunda)

    project_id = _crear_proyecto(client)
    data = _subir_plano(client, project_id)

    assert data["pieza_extraida"]["pieza"] == "pieza_pasada_1"
    # NOT esperando_confirmacion_extraccion todavia - falta la verificacion
    assert data["etapa"] == "extrayendo"
    assert llamadas_verificar == []


def test_verificar_plano_completa_la_segunda_pasada_y_avanza_etapa(client, monkeypatch):
    import app.api.routes_projects as routes_projects_module

    monkeypatch.setattr(
        routes_projects_module,
        "extraer_primera_pasada",
        lambda *a, **k: ResultadoExtraccion(pieza=_pieza_falsa("pieza_pasada_1"), raw_tool_input={}, stop_reason="tool_use"),
    )
    monkeypatch.setattr(
        routes_projects_module,
        "verificar_segunda_pasada",
        lambda *a, **k: ResultadoExtraccion(pieza=_pieza_falsa("pieza_pasada_2_verificada"), raw_tool_input={}, stop_reason="tool_use"),
    )

    project_id = _crear_proyecto(client)
    _subir_plano(client, project_id)

    resp = client.post(f"/api/projects/{project_id}/plano/verificar")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["pieza_extraida"]["pieza"] == "pieza_pasada_2_verificada"
    assert data["etapa"] == "esperando_confirmacion_extraccion"


def test_verificar_plano_sin_primera_pasada_da_409(client):
    project_id = _crear_proyecto(client)
    resp = client.post(f"/api/projects/{project_id}/plano/verificar")
    assert resp.status_code == 409


def test_verificar_plano_si_falla_usa_la_primera_pasada_y_avisa(client, monkeypatch):
    """The review pass is a quality upgrade, not a hard requirement (same
    principle as the internal fallback in _verificar_y_refinar) - a real
    failure here (network blip, rate limit) must not strand a human with
    an otherwise-usable first-pass result and no way to confirm it.
    """
    import app.api.routes_projects as routes_projects_module

    monkeypatch.setattr(
        routes_projects_module,
        "extraer_primera_pasada",
        lambda *a, **k: ResultadoExtraccion(pieza=_pieza_falsa("pieza_pasada_1"), raw_tool_input={}, stop_reason="tool_use"),
    )

    def _falla(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(routes_projects_module, "verificar_segunda_pasada", _falla)

    project_id = _crear_proyecto(client)
    _subir_plano(client, project_id)

    resp = client.post(f"/api/projects/{project_id}/plano/verificar")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["pieza_extraida"]["pieza"] == "pieza_pasada_1"
    assert data["etapa"] == "esperando_confirmacion_extraccion"  # no se queda atorado
    assert "no se pudo completar" in data["pieza_extraida"]["extraccion"]["notas"]
