"""Capa 4 real-hardware path: app/integrations/windows_bridge.py.

No mock HTTP server needed for the "bridge not running" tests - that IS
the real, unmocked behavior in this sandbox (and on any orchestrator
deployment that isn't the user's own Windows shop-floor PC), so letting
the actual connection attempt to 127.0.0.1:5757 fail is the most honest
way to prove the fallback contract holds. Tests that need a bridge
response monkeypatch the module's own _get/_post seams instead of the
network.
"""

from __future__ import annotations

import base64

import pytest

from app.integrations import windows_bridge
from app.schemas.piece import Dimensiones, FormaBase, Material, Pieza
from app.schemas.project import ToolpathPlan


def _pieza() -> Pieza:
    return Pieza(
        pieza="placa_soporte",
        material=Material(nombre="Aluminio 6061"),
        dimensiones=Dimensiones(forma_base=FormaBase.RECTANGULAR, largo_mm=100, ancho_mm=60, espesor_mm=10),
    )


class _FakeResponse:
    def __init__(self, status_code: int = 200, json_data: dict | None = None, text: str = ""):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text

    @property
    def is_error(self) -> bool:
        return self.status_code >= 400

    def json(self) -> dict:
        return self._json


# --- Bridge genuinely not running (the default on any non-Windows-shop-floor machine) ---


def test_estado_bridge_none_cuando_no_hay_nada_escuchando():
    assert windows_bridge.estado_bridge() is None


def test_generar_modelo_solidworks_none_cuando_bridge_no_alcanzable():
    assert windows_bridge.generar_modelo_solidworks(_pieza()) is None


def test_generar_codigo_g_mastercam_none_cuando_bridge_no_alcanzable():
    plan = ToolpathPlan(estrategia="perfil_exterior")
    assert windows_bridge.generar_codigo_g_mastercam(_pieza(), plan, "haas_vf_generico") is None


# --- Bridge reachable but reports the target software unavailable (503) ---


def test_generar_modelo_solidworks_none_cuando_bridge_responde_503(monkeypatch):
    monkeypatch.setattr(windows_bridge, "_post", lambda path, payload: _FakeResponse(status_code=503))
    assert windows_bridge.generar_modelo_solidworks(_pieza()) is None


# --- Bridge reachable and SolidWorks/Mastercam genuinely available ---


def test_generar_modelo_solidworks_devuelve_datos_del_bridge(monkeypatch):
    payload = {
        "archivo_step_base64": base64.b64encode(b"STEP-DATA").decode(),
        "archivo_stl_base64": base64.b64encode(b"STL-DATA").decode(),
        "nombre_archivo": "placa_soporte",
        "advertencias": ["barreno_roscado modelado como liso"],
        "features_omitidos": [],
        "propiedades_geometricas": {"volumen_mm3": 60000.0, "area_superficial_mm2": 32000.0, "bbox_mm": {"x": 100, "y": 60, "z": 10}},
    }
    monkeypatch.setattr(windows_bridge, "_post", lambda path, body: _FakeResponse(status_code=200, json_data=payload))

    data = windows_bridge.generar_modelo_solidworks(_pieza())

    assert data == payload


def test_generar_codigo_g_mastercam_devuelve_datos_del_bridge(monkeypatch):
    payload = {
        "contenido": "G0 X0 Y0\nG1 Z-1 F100\n",
        "operaciones_con_movimiento_real": 1,
        "operaciones_solo_planeadas": 0,
        "advertencias": [],
        "es_simulacion": False,
    }
    monkeypatch.setattr(windows_bridge, "_post", lambda path, body: _FakeResponse(status_code=200, json_data=payload))
    plan = ToolpathPlan(estrategia="perfil_exterior")

    data = windows_bridge.generar_codigo_g_mastercam(_pieza(), plan, "haas_vf_generico")

    assert data == payload


# --- Bridge reachable, DID attempt the call, and it genuinely failed ---
# This must raise, not silently fall back - a real attempted failure looks
# nothing like "no bridge here" and must reach the user.


def test_generar_modelo_solidworks_lanza_bridge_error_si_la_llamada_falla(monkeypatch):
    monkeypatch.setattr(windows_bridge, "_post", lambda path, body: _FakeResponse(status_code=500, text="COM exception"))
    with pytest.raises(windows_bridge.BridgeError):
        windows_bridge.generar_modelo_solidworks(_pieza())


def test_generar_codigo_g_mastercam_lanza_bridge_error_si_la_llamada_falla(monkeypatch):
    monkeypatch.setattr(windows_bridge, "_post", lambda path, body: _FakeResponse(status_code=500, text="fallo"))
    plan = ToolpathPlan(estrategia="perfil_exterior")
    with pytest.raises(windows_bridge.BridgeError):
        windows_bridge.generar_codigo_g_mastercam(_pieza(), plan, "haas_vf_generico")


# --- "Ver en SolidWorks" / "Abrir en Mastercam" (activar_solidworks / abrir_mastercam) ---
# Unlike the generation functions, these always raise on any failure -
# there's no "silently fall back to simulation" option that makes sense
# for a button whose entire point is "show me the real thing".


def test_activar_solidworks_lanza_si_bridge_no_alcanzable():
    with pytest.raises(windows_bridge.BridgeError):
        windows_bridge.activar_solidworks()


def test_activar_solidworks_ok_cuando_bridge_confirma(monkeypatch):
    monkeypatch.setattr(windows_bridge, "_post", lambda path, body: _FakeResponse(status_code=200, json_data={"activado": True}))
    assert windows_bridge.activar_solidworks() is True


def test_activar_solidworks_lanza_con_mensaje_del_bridge_si_falla(monkeypatch):
    monkeypatch.setattr(
        windows_bridge,
        "_post",
        lambda path, body: _FakeResponse(status_code=409, json_data={"detail": "No hay ningun modelo generado en esta sesion del bridge todavia."}),
    )
    with pytest.raises(windows_bridge.BridgeError, match="No hay ningun modelo"):
        windows_bridge.activar_solidworks()


def test_abrir_mastercam_lanza_si_bridge_no_alcanzable():
    with pytest.raises(windows_bridge.BridgeError):
        windows_bridge.abrir_mastercam("/data/projects/AXC-1/files/placa.step")


def test_abrir_mastercam_ok_cuando_bridge_confirma(monkeypatch):
    monkeypatch.setattr(windows_bridge, "_post", lambda path, body: _FakeResponse(status_code=200, json_data={"activado": True}))
    assert windows_bridge.abrir_mastercam("/data/projects/AXC-1/files/placa.step") is True
