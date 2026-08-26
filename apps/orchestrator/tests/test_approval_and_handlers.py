import pytest

from app.agent import approval
from app.schemas.piece import Dimensiones, Feature, FormaBase, Material, Pieza, Posicion2D, TipoFeature
from app.schemas.project import Etapa, Proyecto
from app.tools import handlers


def _pieza() -> Pieza:
    return Pieza(
        pieza="placa_soporte",
        material=Material(nombre="Aluminio 6061"),
        dimensiones=Dimensiones(forma_base=FormaBase.RECTANGULAR, largo_mm=100, ancho_mm=60, espesor_mm=10),
        features=[Feature(id="f1", tipo=TipoFeature.BARRENO, diametro_mm=8, posicion=Posicion2D(x=50, y=30))],
    )


def _proyecto_recien_extraido() -> Proyecto:
    p = Proyecto(nombre="placa_soporte", etapa=Etapa.ESPERANDO_CONFIRMACION_EXTRACCION)
    p.pieza_extraida = _pieza()
    return p


# --- Capa 6: los tres checkpoints deben respetar el orden ---


def test_confirmar_extraccion_avanza_etapa():
    p = _proyecto_recien_extraido()
    approval.confirmar_extraccion(p)
    assert p.pieza_confirmada is True
    assert p.etapa == Etapa.MODELANDO


def test_confirmar_extraccion_fuera_de_orden_falla():
    p = Proyecto(nombre="x", etapa=Etapa.PLANO_SUBIDO)
    with pytest.raises(approval.TransicionInvalida):
        approval.confirmar_extraccion(p)


# --- Capa 4 handlers: no deben avanzar sin el checkpoint humano correspondiente ---


def test_generar_modelo_3d_sin_confirmacion_lanza_precondicion():
    p = _proyecto_recien_extraido()  # pieza_confirmada aun es False
    with pytest.raises(handlers.PrecondicionNoCumplida):
        handlers.generar_modelo_3d(p)


def test_pipeline_completo_respeta_los_dos_checkpoints(tmp_path, monkeypatch):
    """Axiscam's scope is CAD only (plano -> STEP/STL) - see
    approval.confirmar_modelo's docstring. Confirming the model is the
    LAST checkpoint now, not a gate before toolpath planning/G-code (that
    engine still exists in app/cam/*.py and is still tested on its own in
    test_cam.py, it's just not wired into this approval flow anymore).
    """
    monkeypatch.setattr(handlers.storage, "ruta_archivo_generado", lambda project_id, nombre: tmp_path / nombre)

    p = _proyecto_recien_extraido()

    # checkpoint 1
    approval.confirmar_extraccion(p)
    assert p.etapa == Etapa.MODELANDO

    resultado_modelo = handlers.generar_modelo_3d(p)
    assert resultado_modelo["archivos_generados"]
    assert p.etapa == Etapa.ESPERANDO_CONFIRMACION_MODELO

    # checkpoint 2 - final
    approval.confirmar_modelo(p)
    assert p.etapa == Etapa.APROBADO
    assert p.modelo_confirmado is True


# --- Capa 4 handlers deben preferir el bridge de Windows real cuando esta disponible ---


def test_generar_modelo_3d_usa_bridge_real_cuando_esta_disponible(tmp_path, monkeypatch):
    import base64

    def _guardar_bytes(project_id, nombre, contenido):
        ruta = tmp_path / nombre
        ruta.write_bytes(contenido)
        return ruta

    monkeypatch.setattr(handlers.storage, "guardar_bytes", _guardar_bytes)
    monkeypatch.setattr(
        handlers.windows_bridge,
        "generar_modelo_solidworks",
        lambda pieza: {
            "archivo_step_base64": base64.b64encode(b"STEP").decode(),
            "archivo_stl_base64": base64.b64encode(b"STL").decode(),
            "nombre_archivo": "placa_soporte",
            "advertencias": [],
            "features_omitidos": [],
            "propiedades_geometricas": {"volumen_mm3": 1.0, "area_superficial_mm2": 1.0, "bbox_mm": {"x": 1, "y": 1, "z": 1}},
        },
    )

    p = _proyecto_recien_extraido()
    approval.confirmar_extraccion(p)

    resultado = handlers.generar_modelo_3d(p)

    assert resultado["generado_con"] == "solidworks_real"
    assert p.etapa == Etapa.ESPERANDO_CONFIRMACION_MODELO
    assert all(a.es_simulacion is False for a in p.archivos)


def test_generar_modelo_3d_propaga_bridge_error_sin_caer_a_simulacion(monkeypatch):
    def _falla(pieza):
        raise handlers.windows_bridge.BridgeError("SOLIDWORKS lanzo una excepcion COM")

    monkeypatch.setattr(handlers.windows_bridge, "generar_modelo_solidworks", _falla)

    p = _proyecto_recien_extraido()
    approval.confirmar_extraccion(p)

    with pytest.raises(handlers.windows_bridge.BridgeError):
        handlers.generar_modelo_3d(p)
    assert p.etapa == Etapa.ERROR
