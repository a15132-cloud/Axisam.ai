"""POST /api/convertir/step-a-stl - lets the standalone "Simulación" tool
accept the same STEP file real CAD/CAM software uses, converting it
server-side to the triangle mesh a browser can actually draw. Uses a real
STEP file built by the same geometry engine the rest of Axiscam uses, not
a hand-crafted fixture, so this exercises the real cadquery import/export
round trip.
"""

from __future__ import annotations

import io

from fastapi.testclient import TestClient

from app.geometry.builder import build_pieza
from app.geometry.export import exportar_step
from app.main import app
from app.schemas.piece import Dimensiones, FormaBase, Material, Pieza

client = TestClient(app)


def _step_de_prueba(tmp_path) -> bytes:
    pieza = Pieza(
        pieza="cubo_prueba",
        material=Material(nombre="Aluminio 6061"),
        dimensiones=Dimensiones(forma_base=FormaBase.RECTANGULAR, largo_mm=50, ancho_mm=30, espesor_mm=10),
    )
    resultado = build_pieza(pieza)
    ruta = exportar_step(resultado.solido, tmp_path / "cubo_prueba.step")
    return ruta.read_bytes()


def test_step_a_stl_convierte_un_step_real(tmp_path):
    step_bytes = _step_de_prueba(tmp_path)

    resp = client.post(
        "/api/convertir/step-a-stl",
        files={"archivo": ("cubo_prueba.step", io.BytesIO(step_bytes), "application/step")},
    )

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "model/stl"
    # cadquery's default STL export is binary (same call app/geometry/export.py's
    # exportar_stl already uses for every project's own STL download, which the
    # existing viewer already parses fine - not asserting the ASCII "solid" header.
    assert len(resp.content) > 200


def test_step_a_stl_rechaza_archivo_vacio():
    resp = client.post(
        "/api/convertir/step-a-stl",
        files={"archivo": ("vacio.step", io.BytesIO(b""), "application/step")},
    )
    assert resp.status_code == 422


def test_step_a_stl_rechaza_contenido_invalido():
    resp = client.post(
        "/api/convertir/step-a-stl",
        files={"archivo": ("no_es_step.step", io.BytesIO(b"esto no es un archivo STEP valido"), "application/step")},
    )
    assert resp.status_code == 422
    assert "STEP" in resp.json()["detail"]
