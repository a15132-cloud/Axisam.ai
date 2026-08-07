import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.schemas.piece import Dimensiones, Feature, FormaBase, Material, Pieza, Posicion2D, TipoFeature
from app.schemas.project import ArchivoGenerado, Etapa, Proyecto
from app.storage import bundle


def _proyecto_con_archivos(tmp_path) -> Proyecto:
    p = Proyecto(nombre="placa_soporte", etapa=Etapa.APROBADO)
    p.pieza_extraida = Pieza(
        pieza="placa_soporte",
        material=Material(nombre="Aluminio 6061"),
        dimensiones=Dimensiones(forma_base=FormaBase.RECTANGULAR, largo_mm=100, ancho_mm=60, espesor_mm=10),
        features=[Feature(id="f1", tipo=TipoFeature.BARRENO, diametro_mm=8, posicion=Posicion2D(x=50, y=30))],
    )
    p.aprobacion_final = True
    p.aprobado_por = "taller@axiscam"

    step_path = tmp_path / "placa_soporte.step"
    step_path.write_text("ISO-10303-21; fake step content")
    gcode_path = tmp_path / "placa_soporte.nc"
    gcode_path.write_text("(fake gcode)\nM30")

    p.archivos = [
        ArchivoGenerado(nombre="placa_soporte.step", tipo="step", ruta=str(step_path), es_simulacion=False),
        ArchivoGenerado(nombre="placa_soporte.nc", tipo="gcode", ruta=str(gcode_path), es_simulacion=True),
    ]
    return p


def test_generar_resumen_incluye_datos_clave(tmp_path):
    proyecto = _proyecto_con_archivos(tmp_path)
    resumen = bundle.generar_resumen_texto(proyecto)

    assert "placa_soporte" in resumen
    assert "Aluminio 6061" in resumen
    assert "taller@axiscam" in resumen
    assert "AVISO IMPORTANTE" in resumen
    assert "placa_soporte.step" in resumen
    assert "placa_soporte.nc" in resumen


def test_generar_zip_contiene_resumen_y_archivos(tmp_path):
    proyecto = _proyecto_con_archivos(tmp_path)
    contenido = bundle.generar_zip(proyecto)

    with zipfile.ZipFile(io.BytesIO(contenido)) as zf:
        nombres = zf.namelist()
        assert "RESUMEN.txt" in nombres
        assert "placa_soporte.step" in nombres
        assert "placa_soporte.nc" in nombres
        assert b"ISO-10303-21" in zf.read("placa_soporte.step")


def test_generar_zip_omite_archivos_que_ya_no_existen_en_disco(tmp_path):
    proyecto = _proyecto_con_archivos(tmp_path)
    proyecto.archivos.append(ArchivoGenerado(nombre="fantasma.stl", tipo="stl", ruta=str(tmp_path / "no_existe.stl")))
    contenido = bundle.generar_zip(proyecto)
    with zipfile.ZipFile(io.BytesIO(contenido)) as zf:
        assert "fantasma.stl" not in zf.namelist()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AXISCAM_STORAGE_DIR", str(tmp_path))
    import app.config as config_module

    monkeypatch.setattr(config_module, "settings", config_module._load())

    import importlib

    import app.storage.files as storage_module

    importlib.reload(storage_module)

    import app.api.routes_files as routes_files_module

    monkeypatch.setattr(routes_files_module, "storage", storage_module)

    from app.main import app

    return TestClient(app)


def test_endpoint_descargar_todo_devuelve_zip_valido(client, tmp_path, monkeypatch):
    import app.api.routes_files as routes_files_module

    proyecto = _proyecto_con_archivos(tmp_path)
    routes_files_module.storage.guardar_proyecto(proyecto)

    resp = client.get(f"/api/projects/{proyecto.id}/descargar-todo")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert "attachment" in resp.headers["content-disposition"]

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        assert "RESUMEN.txt" in zf.namelist()


def test_endpoint_descargar_todo_404_sin_archivos(client):
    import app.api.routes_files as routes_files_module

    proyecto = Proyecto(nombre="vacio")
    routes_files_module.storage.guardar_proyecto(proyecto)

    resp = client.get(f"/api/projects/{proyecto.id}/descargar-todo")
    assert resp.status_code == 404
