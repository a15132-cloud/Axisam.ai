"""POST /plano/buscar-medidas-faltantes - a real user asked directly for a
way to tell Axiscam "look again for what you didn't find" instead of just
being told to fill it in by hand. See buscar_campos_faltantes' docstring
in app/vision/extractor.py.
"""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

from app.schemas.piece import Dimensiones, ExtraccionMeta, FormaBase, Material, Pieza
from app.vision.extractor import ExtraccionError, ResultadoExtraccion


def _pieza_falsa(nombre: str, campos_baja_confianza: list[str] | None = None) -> Pieza:
    return Pieza(
        pieza=nombre,
        material=Material(nombre="Aluminio 6061"),
        dimensiones=Dimensiones(forma_base=FormaBase.RECTANGULAR, largo_mm=100, ancho_mm=60, espesor_mm=10),
        extraccion=ExtraccionMeta(confianza_global=0.8, campos_baja_confianza=campos_baja_confianza or []),
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


def _proyecto_listo_para_confirmar(client: TestClient, monkeypatch, campos_baja_confianza: list[str]) -> str:
    import app.api.routes_projects as routes_projects_module

    monkeypatch.setattr(
        routes_projects_module,
        "extraer_primera_pasada",
        lambda *a, **k: ResultadoExtraccion(pieza=_pieza_falsa("pieza_v1", campos_baja_confianza), raw_tool_input={}, stop_reason="tool_use"),
    )
    monkeypatch.setattr(
        routes_projects_module,
        "verificar_segunda_pasada",
        lambda *a, **k: ResultadoExtraccion(pieza=_pieza_falsa("pieza_v1", campos_baja_confianza), raw_tool_input={}, stop_reason="tool_use"),
    )

    project_id = client.post("/api/projects", json={"nombre": "test buscar faltantes"}).json()["id"]
    client.post(
        f"/api/projects/{project_id}/plano",
        files={"archivo": ("plano.pdf", b"%PDF-1.4\n%fake", "application/pdf")},
    )
    resp = client.post(f"/api/projects/{project_id}/plano/verificar")
    assert resp.status_code == 200, resp.text
    return project_id


def test_buscar_medidas_faltantes_actualiza_la_pieza(client, monkeypatch):
    import app.api.routes_projects as routes_projects_module

    project_id = _proyecto_listo_para_confirmar(client, monkeypatch, ["espesor_mm"])

    monkeypatch.setattr(
        routes_projects_module,
        "buscar_campos_faltantes",
        lambda *a, **k: ResultadoExtraccion(pieza=_pieza_falsa("pieza_v2_resuelta", []), raw_tool_input={}, stop_reason="tool_use"),
    )

    resp = client.post(f"/api/projects/{project_id}/plano/buscar-medidas-faltantes")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["pieza_extraida"]["pieza"] == "pieza_v2_resuelta"
    assert data["pieza_extraida"]["extraccion"]["campos_baja_confianza"] == []
    assert data["etapa"] == "esperando_confirmacion_extraccion"  # se queda en el mismo checkpoint


def test_buscar_medidas_faltantes_sin_campos_pendientes_da_409(client, monkeypatch):
    project_id = _proyecto_listo_para_confirmar(client, monkeypatch, [])  # nada de baja confianza

    resp = client.post(f"/api/projects/{project_id}/plano/buscar-medidas-faltantes")
    assert resp.status_code == 409


def test_buscar_medidas_faltantes_antes_de_confirmacion_da_409(client):
    project_id = client.post("/api/projects", json={"nombre": "test"}).json()["id"]
    resp = client.post(f"/api/projects/{project_id}/plano/buscar-medidas-faltantes")
    assert resp.status_code == 409


def test_buscar_medidas_faltantes_error_real_no_se_esconde(client, monkeypatch):
    """Unlike verificar_plano, this must NOT silently fall back - the user
    explicitly asked for this one extra look, so a genuine failure has to
    reach them, not disappear as if nothing happened.
    """
    import app.api.routes_projects as routes_projects_module

    project_id = _proyecto_listo_para_confirmar(client, monkeypatch, ["espesor_mm"])

    def _falla(*a, **k):
        raise ExtraccionError("el plano no se pudo volver a leer")

    monkeypatch.setattr(routes_projects_module, "buscar_campos_faltantes", _falla)

    resp = client.post(f"/api/projects/{project_id}/plano/buscar-medidas-faltantes")
    assert resp.status_code == 422
    assert "no se pudo volver a leer" in resp.json()["detail"]
