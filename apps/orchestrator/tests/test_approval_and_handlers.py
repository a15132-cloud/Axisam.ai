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


def test_aprobar_final_requiere_simulacion_previa():
    p = _proyecto_recien_extraido()
    with pytest.raises(approval.TransicionInvalida):
        approval.aprobar_final(p, aprobado_por="taller@axiscam")


# --- Capa 4 handlers: no deben avanzar sin el checkpoint humano correspondiente ---


def test_generar_modelo_3d_sin_confirmacion_lanza_precondicion():
    p = _proyecto_recien_extraido()  # pieza_confirmada aun es False
    with pytest.raises(handlers.PrecondicionNoCumplida):
        handlers.generar_modelo_3d(p)


def test_pipeline_completo_respeta_los_tres_checkpoints(tmp_path, monkeypatch):
    def _guardar_texto(project_id, nombre, contenido):
        ruta = tmp_path / nombre
        ruta.write_text(contenido)
        return ruta

    monkeypatch.setattr(handlers.storage, "ruta_archivo_generado", lambda project_id, nombre: tmp_path / nombre)
    monkeypatch.setattr(handlers.storage, "guardar_texto", _guardar_texto)

    p = _proyecto_recien_extraido()

    # checkpoint 1
    approval.confirmar_extraccion(p)
    assert p.etapa == Etapa.MODELANDO

    resultado_modelo = handlers.generar_modelo_3d(p)
    assert resultado_modelo["archivos_generados"]
    assert p.etapa == Etapa.ESPERANDO_CONFIRMACION_MODELO

    # generar trayectorias antes de confirmar el modelo debe fallar
    with pytest.raises(handlers.PrecondicionNoCumplida):
        handlers.generar_trayectorias(p)

    # checkpoint 2
    approval.confirmar_modelo(p)
    assert p.etapa == Etapa.GENERANDO_TRAYECTORIAS

    handlers.generar_trayectorias(p)
    assert p.toolpath_plan is not None

    resumen = handlers.simular_maquinado(p)
    assert resumen["es_simulacion"] is True
    assert p.etapa == Etapa.ESPERANDO_APROBACION_FINAL

    # exportar codigo G antes de la aprobacion final debe fallar
    with pytest.raises(handlers.PrecondicionNoCumplida):
        handlers.exportar_codigo_g(p)

    # checkpoint 3
    approval.aprobar_final(p, aprobado_por="taller@axiscam")
    assert p.etapa == Etapa.APROBADO

    resultado_gcode = handlers.exportar_codigo_g(p)
    assert resultado_gcode["es_simulacion"] is True
    assert any(a.tipo == "gcode" for a in p.archivos)
