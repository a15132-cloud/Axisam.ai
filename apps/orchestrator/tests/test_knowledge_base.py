import pytest

from app.knowledge_base import rules
from app.schemas.piece import Feature, Material, TipoFeature


def test_buscar_material_conocido():
    info = rules.buscar_material(Material(nombre="Aluminio 6061"))
    assert info["clave"] == "aluminio_6061"
    assert info["vc_recomendada_m_min"] == 300


def test_buscar_material_desconocido_lanza_error():
    with pytest.raises(rules.MaterialNoEncontrado):
        rules.buscar_material(Material(nombre="Unobtainium"))


def test_seleccionar_broca_exacta():
    h = rules.seleccionar_broca(8.0)
    assert h.diametro_mm == 8.0
    assert h.exacta


def test_seleccionar_broca_redondea_hacia_arriba():
    h = rules.seleccionar_broca(7.2)
    assert h.diametro_mm == 8.0
    assert not h.exacta


def test_planear_operacion_barreno():
    feature = Feature(tipo=TipoFeature.BARRENO, diametro_mm=8.0, tolerancia_mm=0.05, cantidad=4)
    op = rules.planear_operacion(feature, Material(nombre="Aluminio 6061"), espesor_pieza_mm=10.0)
    assert op.herramienta.tipo == "broca"
    assert op.herramienta.diametro_mm == 8.0
    assert op.parametros.rpm > 0
    assert "ciclo fijo" in op.estrategia.lower() or "G81" in op.estrategia


def test_planear_operacion_material_no_validado_advierte():
    feature = Feature(tipo=TipoFeature.BARRENO, diametro_mm=8.0)
    op = rules.planear_operacion(feature, Material(nombre="Aluminio 6061"), espesor_pieza_mm=10.0)
    assert any("sin validar" in w for w in op.parametros.advertencias)


def test_obtener_postprocesador_default_es_haas():
    pp = rules.obtener_postprocesador()
    assert pp["controlador"] == "haas"


def test_obtener_postprocesador_desconocido():
    with pytest.raises(ValueError):
        rules.obtener_postprocesador("no_existe")
