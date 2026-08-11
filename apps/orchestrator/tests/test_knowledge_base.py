import pytest

from app.knowledge_base import rules
from app.schemas.piece import Feature, Material, TipoFeature


def test_buscar_material_conocido():
    info = rules.buscar_material(Material(nombre="Aluminio 6061"))
    assert info["clave"] == "aluminio_6061"
    assert info["vc_recomendada_m_min"] == 300


def test_buscar_material_d2_por_nombre_de_cliente_real():
    """D2 added specifically after a real customer drawing (DeAcero) used
    it and had zero CAM operations planned as a result - MaterialNoEncontrado
    silently meant "no G-code at all" for a real hardened-tool-steel part.
    """
    info = rules.buscar_material(Material(nombre="D2"))
    assert info["clave"] == "d2"
    assert info["vc_recomendada_m_min"] > 0
    assert info["refrigerante"] == "requerido"


def test_buscar_material_desconocido_lanza_error():
    with pytest.raises(rules.MaterialNoEncontrado):
        rules.buscar_material(Material(nombre="Unobtainium"))


def test_buscar_material_con_texto_extra_como_lo_escribe_claude_real():
    """Real bug caught live against the deployed backend: Claude extracted
    the material as "Acero SAE D2" (completely normal, human-natural
    phrasing) from a real customer drawing. Neither the exact-match nor
    the old nombre_display-substring fallback caught it (the tokens are in
    a different order than the catalog's own display string), so the ENTIRE
    toolpath plan for a real 6-hole part came back with zero operations -
    an "approved" G-code file that didn't cut a single hole, with no error
    shown anywhere except a warning buried in advertencias.
    """
    info = rules.buscar_material(Material(nombre="Acero SAE D2"))
    assert info["clave"] == "d2"


def test_buscar_material_designacion_con_sufijo_de_temple():
    info = rules.buscar_material(Material(nombre="Aluminio 6061-T6"))
    assert info["clave"] == "aluminio_6061"


def test_seleccionar_broca_exacta():
    h = rules.seleccionar_broca(8.0)
    assert h.diametro_mm == 8.0
    assert h.exacta


def test_seleccionar_broca_redondea_hacia_arriba():
    h = rules.seleccionar_broca(7.2)
    assert h.diametro_mm == 8.0
    assert not h.exacta


def test_seleccionar_broca_22mm_por_pieza_de_cliente_real():
    """Ø22 added specifically after the DeAcero drawing's 6 mounting holes
    (22mm H-fit) fell out of catalog range (previously topped at 20mm) and
    silently machined with the wrong tool diameter - RPM/feed were computed
    for 20mm, not the 22mm the drawing actually calls for.
    """
    h = rules.seleccionar_broca(22.0)
    assert h.diametro_mm == 22.0
    assert h.exacta


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


def test_planear_operacion_material_desconocido_igual_planea_algo_real():
    """The other half of the real bug fixed here: even a material that
    truly isn't in the catalog (not just a naming-drift miss) must not
    zero out the feature entirely - app/cam/planner.py used to catch
    MaterialNoEncontrado and `continue`, skipping the feature, which for
    a piece where EVERY feature shares the same unrecognized material
    meant a G-code file with no real operations at all. A conservative,
    loudly-flagged fallback must still produce a real, usable operation.
    """
    feature = Feature(tipo=TipoFeature.BARRENO, diametro_mm=8.0)
    op = rules.planear_operacion(feature, Material(nombre="Unobtainium Exotico"), espesor_pieza_mm=10.0)

    assert op.herramienta.diametro_mm == 8.0
    assert op.parametros.rpm > 0
    assert any("Unobtainium Exotico" in n and "generico" in n for n in op.notas)
    assert any("sin validar" in w for w in op.parametros.advertencias)


def test_planear_trayectoria_no_queda_vacia_por_material_desconocido():
    """Same bug, at the layer the user actually sees: a full piece plan
    must still produce real operations (and thus real G-code motion) even
    when the material can't be resolved at all - not zero operations that
    quietly render an "approved" file useless.
    """
    from app.cam.planner import planear_trayectoria
    from app.schemas.piece import Dimensiones, FormaBase, Pieza, Posicion2D

    pieza = Pieza(
        pieza="pieza_material_raro",
        material=Material(nombre="Unobtainium Exotico"),
        dimensiones=Dimensiones(forma_base=FormaBase.RECTANGULAR, largo_mm=100, ancho_mm=60, espesor_mm=10),
        features=[Feature(tipo=TipoFeature.BARRENO, diametro_mm=8.0, posicion=Posicion2D(x=50, y=30))],
    )
    plan = planear_trayectoria(pieza)

    assert len(plan.operaciones) == 1
    assert any("Unobtainium Exotico" in w for w in plan.plan.advertencias)


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
