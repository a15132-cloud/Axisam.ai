"""Anthropic-error-to-HTTP mapping for the chat and plano-upload endpoints
(app/api/routes_projects.py::_http_desde_error_anthropic).

Found by actually curling these endpoints with a fake API key during
manual testing: a bad key used to surface as a raw 500 "Internal Server
Error" with the full Anthropic exception dumped into the body. Axiscam
uses one shared ANTHROPIC_API_KEY configured by whoever deploys the
backend (see render.yaml) - end clients never see or configure an API
key themselves, the same way a ChatGPT/Perplexity user never does. So
these responses must stay professional and jargon-free: no "API key" or
setup instructions in anything a client-facing chat could show, only a
generic "not available right now" message. The real exception detail
still lands in the project's activity log for the operator to diagnose.
"""

from __future__ import annotations

import importlib

import anthropic
import httpx
import pytest
from fastapi.testclient import TestClient


def _fake_auth_error() -> anthropic.AuthenticationError:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(status_code=401, request=request, json={"error": {"message": "invalid x-api-key"}})
    return anthropic.AuthenticationError("invalid x-api-key", response=response, body=None)


def _fake_rate_limit_error() -> anthropic.RateLimitError:
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(status_code=429, request=request, json={"error": {"message": "rate limited"}})
    return anthropic.RateLimitError("rate limited", response=response, body=None)


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
    resp = client.post("/api/projects", json={"nombre": "test byok"})
    assert resp.status_code == 200
    return resp.json()["id"]


def _sin_jerga_tecnica(mensaje: str) -> bool:
    prohibido = ("api key", "api-key", "anthropic_api_key", "console.anthropic.com")
    return not any(p in mensaje.lower() for p in prohibido)


def test_chat_sin_key_configurada_en_servidor_da_mensaje_profesional(client):
    project_id = _crear_proyecto(client)
    resp = client.post(f"/api/projects/{project_id}/chat", json={"mensaje": "hola"})
    assert resp.status_code == 503
    assert _sin_jerga_tecnica(resp.json()["detail"])


def test_chat_con_key_del_servidor_invalida_da_503_no_500(client, monkeypatch):
    import app.api.routes_projects as routes_projects_module

    def _falla(*args, **kwargs):
        raise _fake_auth_error()

    monkeypatch.setattr(routes_projects_module, "ejecutar_turno", _falla)

    project_id = _crear_proyecto(client)
    resp = client.post(f"/api/projects/{project_id}/chat", json={"mensaje": "hola"})

    assert resp.status_code == 503
    assert _sin_jerga_tecnica(resp.json()["detail"])


def test_chat_con_rate_limit_devuelve_429(client, monkeypatch):
    import app.api.routes_projects as routes_projects_module

    def _falla(*args, **kwargs):
        raise _fake_rate_limit_error()

    monkeypatch.setattr(routes_projects_module, "ejecutar_turno", _falla)

    project_id = _crear_proyecto(client)
    resp = client.post(f"/api/projects/{project_id}/chat", json={"mensaje": "hola"})

    assert resp.status_code == 429
    assert _sin_jerga_tecnica(resp.json()["detail"])


def test_subir_plano_con_key_del_servidor_invalida_da_503_no_500(client, monkeypatch, tmp_path):
    import app.api.routes_projects as routes_projects_module

    def _falla(*args, **kwargs):
        raise _fake_auth_error()

    monkeypatch.setattr(routes_projects_module, "extraer_pieza_desde_plano", _falla)

    project_id = _crear_proyecto(client)
    archivo = tmp_path / "plano.pdf"
    archivo.write_bytes(b"%PDF-1.4\n%fake")

    with archivo.open("rb") as f:
        resp = client.post(
            f"/api/projects/{project_id}/plano",
            files={"archivo": ("plano.pdf", f, "application/pdf")},
        )

    assert resp.status_code == 503
    assert _sin_jerga_tecnica(resp.json()["detail"])


def test_subir_plano_sin_key_configurada_en_servidor_da_mensaje_profesional(client, monkeypatch, tmp_path):
    import app.api.routes_projects as routes_projects_module

    def _falla(*args, **kwargs):
        raise RuntimeError("ANTHROPIC_API_KEY no esta configurada en el servidor - ...")

    monkeypatch.setattr(routes_projects_module, "extraer_pieza_desde_plano", _falla)

    project_id = _crear_proyecto(client)
    archivo = tmp_path / "plano.pdf"
    archivo.write_bytes(b"%PDF-1.4\n%fake")

    with archivo.open("rb") as f:
        resp = client.post(
            f"/api/projects/{project_id}/plano",
            files={"archivo": ("plano.pdf", f, "application/pdf")},
        )

    assert resp.status_code == 503
    assert _sin_jerga_tecnica(resp.json()["detail"])
