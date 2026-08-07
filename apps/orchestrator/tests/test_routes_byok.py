"""Bring-your-own-key routing (app/api/routes_projects.py::_cliente_de_usuario)
and its Anthropic-error-to-HTTP mapping (_http_desde_error_anthropic).

Found by actually curling these endpoints with a fake API key during
manual testing: a bad key used to surface as a raw 500 "Internal Server
Error" with the full Anthropic exception dumped into the body - unusable
for a non-technical user trying to fix their own key. These tests pin
the fix: a bad/missing key must always come back as a clean 401/503 with
an actionable Spanish message, on both the chat and plano-upload paths.
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


def test_chat_sin_key_devuelve_mensaje_accionable(client):
    project_id = _crear_proyecto(client)
    resp = client.post(f"/api/projects/{project_id}/chat", json={"mensaje": "hola"})
    assert resp.status_code == 503
    assert "Configuración" in resp.json()["detail"]


def test_chat_con_key_invalida_devuelve_401_no_500(client, monkeypatch):
    import app.api.routes_projects as routes_projects_module

    def _falla(*args, **kwargs):
        raise _fake_auth_error()

    monkeypatch.setattr(routes_projects_module, "ejecutar_turno", _falla)

    project_id = _crear_proyecto(client)
    resp = client.post(
        f"/api/projects/{project_id}/chat",
        json={"mensaje": "hola"},
        headers={"X-Anthropic-Api-Key": "sk-ant-invalida"},
    )

    assert resp.status_code == 401
    assert "no es válida" in resp.json()["detail"]


def test_chat_con_rate_limit_devuelve_429(client, monkeypatch):
    import app.api.routes_projects as routes_projects_module

    def _falla(*args, **kwargs):
        raise _fake_rate_limit_error()

    monkeypatch.setattr(routes_projects_module, "ejecutar_turno", _falla)

    project_id = _crear_proyecto(client)
    resp = client.post(
        f"/api/projects/{project_id}/chat",
        json={"mensaje": "hola"},
        headers={"X-Anthropic-Api-Key": "sk-ant-valida-pero-sin-credito"},
    )

    assert resp.status_code == 429


def test_subir_plano_con_key_invalida_devuelve_401_no_500(client, monkeypatch, tmp_path):
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
            headers={"X-Anthropic-Api-Key": "sk-ant-invalida"},
        )

    assert resp.status_code == 401
    assert "no es válida" in resp.json()["detail"]
