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


def test_planear_operacion_saliente_recomienda_herramienta_real():
    """A boss (saliente) is machined subtractively by facing the material
    AROUND it down - real tool/speeds/feeds should come back, not the
    "estrategia no definida" fallback a truly unknown feature type gets.
    """
    feature = Feature(tipo=TipoFeature.SALIENTE, diametro_mm=40.0, profundidad_mm=5.0)
    op = rules.planear_operacion(feature, Material(nombre="Aluminio 6061"), espesor_pieza_mm=15.0)
    assert "relieve" in op.estrategia.lower() or "isla" in op.estrategia.lower()
    assert op.herramienta.diametro_mm > 0
    assert op.parametros.rpm > 0


def test_planear_operacion_saliente_usa_holgura_real_para_el_tamano_de_herramienta():
    feature = Feature(tipo=TipoFeature.SALIENTE, diametro_mm=40.0, profundidad_mm=5.0)
    op_amplio = rules.planear_operacion(feature, Material(nombre="Aluminio 6061"), espesor_pieza_mm=15.0, holgura_disponible_mm=20.0)
    op_estrecho = rules.planear_operacion(feature, Material(nombre="Aluminio 6061"), espesor_pieza_mm=15.0, holgura_disponible_mm=3.0)
    assert op_estrecho.herramienta.diametro_mm < op_amplio.herramienta.diametro_mm


def test_planear_operacion_saliente_advierte_si_ni_la_herramienta_mas_chica_cabe():
    feature = Feature(tipo=TipoFeature.SALIENTE, diametro_mm=40.0, profundidad_mm=5.0)
    op = rules.planear_operacion(feature, Material(nombre="Aluminio 6061"), espesor_pieza_mm=15.0, holgura_disponible_mm=0.5)
    assert any("espacio real alrededor" in n for n in op.notas)


def test_obtener_postprocesador_default_es_haas():
    pp = rules.obtener_postprocesador()
    assert pp["controlador"] == "haas"


def test_obtener_postprocesador_desconocido():
    with pytest.raises(ValueError):
        rules.obtener_postprocesador("no_existe")
