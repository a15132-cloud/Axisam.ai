import math
from pathlib import Path

import pytest

from app.geometry.builder import GeometryBuildError, build_pieza
from app.geometry.export import calcular_propiedades, exportar_step, exportar_stl
from app.schemas.piece import Dimensiones, Feature, FormaBase, Material, Pieza, Posicion2D, SegmentoChaflanCompuesto, TipoFeature


def _placa_soporte() -> Pieza:
    return Pieza(
        pieza="placa_soporte",
        material=Material(nombre="Aluminio 6061"),
        dimensiones=Dimensiones(forma_base=FormaBase.RECTANGULAR, largo_mm=100, ancho_mm=60, espesor_mm=10),
        features=[
            Feature(
                id="f1",
                tipo=TipoFeature.BARRENO,
                diametro_mm=8,
                posiciones=[
                    Posicion2D(x=15, y=15),
                    Posicion2D(x=85, y=15),
                    Posicion2D(x=15, y=45),
                    Posicion2D(x=85, y=45),
                ],
                cantidad=4,
                tolerancia_mm=0.05,
            ),
            Feature(id="f2", tipo=TipoFeature.REDONDEO, radio_mm=5),
        ],
        acabado_superficial="Ra 3.2",
    )


def test_build_placa_soporte_sin_errores():
    resultado = build_pieza(_placa_soporte())
    assert resultado.solido is not None
    assert resultado.features_omitidos == []
    props = calcular_propiedades(resultado.solido)
    assert props["bbox_mm"]["z"] == pytest.approx(10.0, abs=0.01)
    # 4 through holes of d=8 remove volume from the 100x60x10 block
    assert props["volumen_mm3"] < 100 * 60 * 10


def test_export_step_and_stl(tmp_path: Path):
    resultado = build_pieza(_placa_soporte())
    step_path = exportar_step(resultado.solido, tmp_path / "placa_soporte.step")
    stl_path = exportar_stl(resultado.solido, tmp_path / "placa_soporte.stl")
    assert step_path.exists() and step_path.stat().st_size > 0
    assert stl_path.exists() and stl_path.stat().st_size > 0


def test_patron_incompleto_genera_advertencia():
    pieza = _placa_soporte()
    pieza.features[0].posiciones = [Posicion2D(x=15, y=15)]  # only 1 of 4
    resultado = build_pieza(pieza)
    assert any("patron completo" in w for w in resultado.advertencias)


def test_forma_base_no_soportada_lanza_error():
    pieza = _placa_soporte()
    pieza.dimensiones.forma_base = FormaBase.REVOLUCION
    with pytest.raises(GeometryBuildError):
        build_pieza(pieza)


def _placa_lisa_para_esquinas() -> Pieza:
    """Same footprint as _placa_soporte but with NO pre-existing corner
    feature, so a test can add exactly one REDONDEO/CHAFLAN without a
    second all-corners feature fighting over the same edges.
    """
    return Pieza(
        pieza="placa_lisa",
        material=Material(nombre="Aluminio 6061"),
        dimensiones=Dimensiones(forma_base=FormaBase.RECTANGULAR, largo_mm=100, ancho_mm=60, espesor_mm=10),
    )


def test_chaflan_45_grados_si_se_modela():
    pieza = _placa_lisa_para_esquinas()
    pieza.features.append(Feature(id="c45", tipo=TipoFeature.CHAFLAN, radio_mm=3, angulo_grados=45))
    resultado = build_pieza(pieza)
    assert not any("c45" in o for o in resultado.features_omitidos)
    props = calcular_propiedades(resultado.solido)
    assert props["volumen_mm3"] < 100 * 60 * 10  # el chaflan si quito material


def test_chaflan_angulo_distinto_a_45_se_omite_en_vez_de_cortarse_mal():
    """cq.chamfer() solo puede garantizar un corte simetrico (45 grados)
    sin saber de cual de las dos caras del corner se mide el angulo - un
    chaflan a 30/60/etc grados modelado "a fuerzas" a 45 seria un STEP que
    parece correcto pero mide mal. Debe omitirse, igual que escalon sin
    profundidad, no cortarse con el angulo equivocado.
    """
    pieza = _placa_lisa_para_esquinas()
    pieza.features.append(Feature(id="c30", tipo=TipoFeature.CHAFLAN, radio_mm=3, angulo_grados=30))
    resultado = build_pieza(pieza)
    assert any("c30" in o and "30" in o for o in resultado.features_omitidos)

    # Y el volumen coincide exactamente con "sin ese chaflan" - no se corto nada por el.
    props_con = calcular_propiedades(resultado.solido)
    props_sin = calcular_propiedades(build_pieza(_placa_lisa_para_esquinas()).solido)
    assert props_con["volumen_mm3"] == pytest.approx(props_sin["volumen_mm3"], abs=0.01)


def test_saliente_agrega_material_no_lo_quita():
    """The whole point of `saliente` is being additive - a boss sticking
    UP off the top face. If this ever regressed to behaving like a cut
    (e.g. someone "simplifies" _agregar_saliente_cilindrico to .cut()),
    both of these assertions would fail immediately.
    """
    base = Pieza(
        pieza="placa_con_boss",
        material=Material(nombre="Aluminio 6061"),
        dimensiones=Dimensiones(forma_base=FormaBase.RECTANGULAR, largo_mm=100, ancho_mm=60, espesor_mm=10),
    )
    con_boss = Pieza(
        pieza="placa_con_boss",
        material=Material(nombre="Aluminio 6061"),
        dimensiones=Dimensiones(forma_base=FormaBase.RECTANGULAR, largo_mm=100, ancho_mm=60, espesor_mm=10),
        features=[Feature(id="boss", tipo=TipoFeature.SALIENTE, diametro_mm=30, profundidad_mm=6, posicion=Posicion2D(x=50, y=30))],
    )

    resultado_base = build_pieza(base)
    resultado_boss = build_pieza(con_boss)
    props_base = calcular_propiedades(resultado_base.solido)
    props_boss = calcular_propiedades(resultado_boss.solido)

    assert props_boss["volumen_mm3"] > props_base["volumen_mm3"]
    assert props_boss["bbox_mm"]["z"] == pytest.approx(16.0, abs=0.01)  # 10mm base + 6mm boss height


def test_saliente_con_barreno_pasante_perfora_el_boss_tambien():
    """A through-hole at the same position as a boss must cut through the
    ADDED boss material too, not just the original base thickness - this
    is exactly the counterbore-like shape (raised boss + hole through the
    middle) that came up on a real customer drawing. Regression test for
    _cortar_barreno's bounding-box-based Z range (see its docstring) -
    the old fixed-espesor range would leave the boss un-pierced.
    """
    pieza = Pieza(
        pieza="placa_con_boss_taladrado",
        material=Material(nombre="Aluminio 6061"),
        dimensiones=Dimensiones(forma_base=FormaBase.RECTANGULAR, largo_mm=100, ancho_mm=60, espesor_mm=10),
        features=[
            Feature(id="boss", tipo=TipoFeature.SALIENTE, diametro_mm=30, profundidad_mm=6, posicion=Posicion2D(x=50, y=30)),
            Feature(id="hoyo", tipo=TipoFeature.BARRENO, diametro_mm=10, pasante=True, posicion=Posicion2D(x=50, y=30)),
        ],
    )

    resultado = build_pieza(pieza)
    props = calcular_propiedades(resultado.solido)

    assert props["bbox_mm"]["z"] == pytest.approx(16.0, abs=0.01)  # boss still there, full height
    # A cylindrical hole (r=5) through 16mm removes ~pi*5^2*16 ~= 1257mm3.
    # If the hole only cut the original 10mm and left the boss solid on
    # top, the removed volume would be ~pi*5^2*10 ~= 785mm3 instead -
    # comparing against the boss-less baseline distinguishes the two.
    base = Pieza(
        pieza="placa_con_boss_taladrado",
        material=Material(nombre="Aluminio 6061"),
        dimensiones=Dimensiones(forma_base=FormaBase.RECTANGULAR, largo_mm=100, ancho_mm=60, espesor_mm=10),
        features=[Feature(id="boss", tipo=TipoFeature.SALIENTE, diametro_mm=30, profundidad_mm=6, posicion=Posicion2D(x=50, y=30))],
    )
    props_sin_hoyo = calcular_propiedades(build_pieza(base).solido)
    volumen_removido = props_sin_hoyo["volumen_mm3"] - props["volumen_mm3"]
    assert volumen_removido == pytest.approx(1256.6, rel=0.02)


def test_base_poligonal_construye_perfil_escalonado():
    """An L-shaped outline (a rectangle with a corner notch) - the exact
    shape of feature a plain rectangular/circular base can't produce,
    which is what forma_base=poligonal exists for.
    """
    perfil = [
        Posicion2D(x=0, y=0),
        Posicion2D(x=100, y=0),
        Posicion2D(x=100, y=40),
        Posicion2D(x=60, y=40),
        Posicion2D(x=60, y=60),
        Posicion2D(x=0, y=60),
    ]
    pieza = Pieza(
        pieza="placa_en_L",
        material=Material(nombre="Aluminio 6061"),
        dimensiones=Dimensiones(forma_base=FormaBase.POLIGONAL, espesor_mm=10, puntos_perfil_mm=perfil),
    )

    resultado = build_pieza(pieza)
    props = calcular_propiedades(resultado.solido)

    assert props["bbox_mm"]["x"] == pytest.approx(100.0, abs=0.01)
    assert props["bbox_mm"]["y"] == pytest.approx(60.0, abs=0.01)
    # The full 100x60 bounding rectangle would be 6000mm2 of footprint;
    # the L-shape (with a 40x20 corner notched out) is 6000 - 800 = 5200mm2.
    assert props["volumen_mm3"] == pytest.approx(5200 * 10, rel=0.001)


def test_base_poligonal_permite_redondeos_de_esquina():
    perfil = [Posicion2D(x=0, y=0), Posicion2D(x=50, y=0), Posicion2D(x=50, y=30), Posicion2D(x=0, y=30)]
    pieza = Pieza(
        pieza="placa_poligonal_redondeada",
        material=Material(nombre="Aluminio 6061"),
        dimensiones=Dimensiones(forma_base=FormaBase.POLIGONAL, espesor_mm=5, puntos_perfil_mm=perfil),
        features=[Feature(id="r1", tipo=TipoFeature.REDONDEO, radio_mm=5)],
    )

    resultado = build_pieza(pieza)

    assert resultado.features_omitidos == []
    assert resultado.advertencias == []


def test_dimensiones_poligonal_requiere_puntos_perfil():
    with pytest.raises(Exception):
        Dimensiones(forma_base=FormaBase.POLIGONAL, espesor_mm=5)


def test_feature_no_soportado_se_omite_no_crashea():
    pieza = _placa_soporte()
    pieza.features.append(Feature(id="f3", tipo=TipoFeature.PERFIL_EXTERIOR, ancho_mm=10, largo_mm=10, profundidad_mm=2))
    resultado = build_pieza(pieza)
    assert any("perfil_exterior" in o for o in resultado.features_omitidos)


def test_escalon_corta_relieve_a_lo_largo_de_todo_el_borde():
    """Found missing on a real client part (a DeAcero shear blade): a
    continuous relief running the full length of one edge, visible in the
    plano as a line parallel to that edge rather than a per-position
    callout. escalon used to be a dead enum value the engine always
    omitted - this is the real implementation.
    """
    pieza = Pieza(
        pieza="placa_con_relieve",
        material=Material(nombre="Aluminio 6061"),
        dimensiones=Dimensiones(forma_base=FormaBase.RECTANGULAR, largo_mm=100, ancho_mm=60, espesor_mm=10),
        features=[Feature(id="relieve", tipo=TipoFeature.ESCALON, cara="lateral_frontal", ancho_mm=8, profundidad_mm=3)],
    )
    resultado = build_pieza(pieza)
    assert resultado.features_omitidos == []
    props = calcular_propiedades(resultado.solido)
    # A block 100x60x10 with an 8mm-wide, 3mm-deep strip removed along the
    # full 100mm length of the Y=0 edge: 100 * 8 * 3 = 2400mm3 removed.
    assert props["volumen_mm3"] == pytest.approx(100 * 60 * 10 - 2400, rel=0.001)
    assert props["bbox_mm"]["x"] == pytest.approx(100.0, abs=0.01)
    assert props["bbox_mm"]["y"] == pytest.approx(60.0, abs=0.01)
    assert props["bbox_mm"]["z"] == pytest.approx(10.0, abs=0.01)


def test_escalon_en_cada_borde_remueve_el_volumen_de_ese_borde_especifico():
    """The relief must actually span the edge it's named for and only that
    edge's length - lateral_frontal/posterior run the 100mm length,
    lateral_izquierda/derecha run the 60mm width, so a 100x60 (non-square)
    base removes a DIFFERENT volume on each pair, which is exactly the
    proof it's cutting along the named edge and not some fixed default.
    """
    esperado = {
        "lateral_frontal": 100 * 8 * 3,
        "lateral_posterior": 100 * 8 * 3,
        "lateral_izquierda": 60 * 8 * 3,
        "lateral_derecha": 60 * 8 * 3,
    }
    for cara, removido_esperado in esperado.items():
        pieza = Pieza(
            pieza="placa_con_relieve",
            material=Material(nombre="Aluminio 6061"),
            dimensiones=Dimensiones(forma_base=FormaBase.RECTANGULAR, largo_mm=100, ancho_mm=60, espesor_mm=10),
            features=[Feature(id="relieve", tipo=TipoFeature.ESCALON, cara=cara, ancho_mm=8, profundidad_mm=3)],
        )
        resultado = build_pieza(pieza)
        assert resultado.features_omitidos == []
        volumen = calcular_propiedades(resultado.solido)["volumen_mm3"]
        assert volumen == pytest.approx(100 * 60 * 10 - removido_esperado, rel=0.001), cara


def test_escalon_con_cara_no_reconocida_lanza_error():
    pieza = Pieza(
        pieza="placa_con_relieve",
        material=Material(nombre="Aluminio 6061"),
        dimensiones=Dimensiones(forma_base=FormaBase.RECTANGULAR, largo_mm=100, ancho_mm=60, espesor_mm=10),
        features=[Feature(id="relieve", tipo=TipoFeature.ESCALON, cara="superior", ancho_mm=8, profundidad_mm=3)],
    )
    with pytest.raises(GeometryBuildError):
        build_pieza(pieza)


def test_escalon_sin_profundidad_se_omite_no_adivina():
    """A relief with a confirmed location/width but no depth anywhere in
    the drawing must be omitted, never built with a guessed depth - unlike
    cajera/ranura, which do default a blind pocket's depth, this feature
    spans an entire edge and is too consequential for that fallback.
    """
    pieza = Pieza(
        pieza="placa_con_relieve",
        material=Material(nombre="Aluminio 6061"),
        dimensiones=Dimensiones(forma_base=FormaBase.RECTANGULAR, largo_mm=100, ancho_mm=60, espesor_mm=10),
        features=[Feature(id="relieve", tipo=TipoFeature.ESCALON, cara="lateral_frontal", ancho_mm=8, profundidad_mm=None)],
    )
    resultado = build_pieza(pieza)
    assert any("escalon" in o and "profundidad" in o for o in resultado.features_omitidos)
    props = calcular_propiedades(resultado.solido)
    assert props["volumen_mm3"] == pytest.approx(100 * 60 * 10, rel=0.001)


def test_escalon_en_base_no_rectangular_se_omite():
    perfil = [Posicion2D(x=0, y=0), Posicion2D(x=50, y=0), Posicion2D(x=50, y=30), Posicion2D(x=0, y=30)]
    pieza = Pieza(
        pieza="placa_poligonal_con_relieve",
        material=Material(nombre="Aluminio 6061"),
        dimensiones=Dimensiones(forma_base=FormaBase.POLIGONAL, espesor_mm=5, puntos_perfil_mm=perfil),
        features=[Feature(id="relieve", tipo=TipoFeature.ESCALON, cara="lateral_frontal", ancho_mm=5, profundidad_mm=1)],
    )
    resultado = build_pieza(pieza)
    assert any("escalon" in o and "rectangular" in o for o in resultado.features_omitidos)


@pytest.mark.parametrize(
    "cara,eje_extremo",
    [
        ("lateral_izquierda", "x"),
        ("lateral_derecha", "x"),
        ("lateral_frontal", "y"),
        ("lateral_posterior", "y"),
    ],
)
def test_barreno_lateral_atraviesa_la_pieza_correcta(cara, eje_extremo):
    import math

    pieza = Pieza(
        pieza="bloque",
        material=Material(nombre="Aluminio 6061"),
        dimensiones=Dimensiones(forma_base=FormaBase.RECTANGULAR, largo_mm=100, ancho_mm=60, espesor_mm=10),
        features=[Feature(id="f1", tipo=TipoFeature.BARRENO, diametro_mm=6, cara=cara, posicion=Posicion2D(x=30, y=5))],
    )
    resultado = build_pieza(pieza)
    assert resultado.features_omitidos == [], resultado.features_omitidos

    props = calcular_propiedades(resultado.solido)
    volumen_esperado = 100 * 60 * 10 - math.pi * 3**2 * (100 if eje_extremo == "x" else 60)
    assert props["volumen_mm3"] == pytest.approx(volumen_esperado, rel=0.01)
    # a full through-hole must not change the part's outer bounding box
    assert props["bbox_mm"]["x"] == pytest.approx(100.0, abs=0.05)
    assert props["bbox_mm"]["y"] == pytest.approx(60.0, abs=0.05)
    assert props["bbox_mm"]["z"] == pytest.approx(10.0, abs=0.05)


def test_barreno_lateral_ciego_no_atraviesa():
    pieza = Pieza(
        pieza="bloque",
        material=Material(nombre="Aluminio 6061"),
        dimensiones=Dimensiones(forma_base=FormaBase.RECTANGULAR, largo_mm=100, ancho_mm=60, espesor_mm=10),
        features=[
            Feature(
                id="f1", tipo=TipoFeature.BARRENO, diametro_mm=6, cara="lateral_izquierda",
                posicion=Posicion2D(x=30, y=5), pasante=False, profundidad_mm=20,
            )
        ],
    )
    resultado = build_pieza(pieza)
    assert resultado.features_omitidos == []
    # a blind hole must not reach all the way through to the opposite face
    assert resultado.solido.val().Volume() > 100 * 60 * 10 - (100 * 60 * 10 * 0.5)


def test_barreno_lateral_cara_desconocida_se_omite():
    pieza = Pieza(
        pieza="bloque",
        material=Material(nombre="Aluminio 6061"),
        dimensiones=Dimensiones(forma_base=FormaBase.RECTANGULAR, largo_mm=100, ancho_mm=60, espesor_mm=10),
        features=[Feature(id="f1", tipo=TipoFeature.BARRENO, diametro_mm=6, cara="lateral_arriba", posicion=Posicion2D(x=30, y=5))],
    )
    resultado = build_pieza(pieza)
    assert any("no reconocida" in o for o in resultado.features_omitidos)


def test_cajera_en_cara_lateral_se_omite_no_crashea():
    pieza = Pieza(
        pieza="bloque",
        material=Material(nombre="Aluminio 6061"),
        dimensiones=Dimensiones(forma_base=FormaBase.RECTANGULAR, largo_mm=100, ancho_mm=60, espesor_mm=10),
        features=[
            Feature(id="f1", tipo=TipoFeature.CAJERA, ancho_mm=10, largo_mm=10, cara="lateral_frontal", posicion=Posicion2D(x=30, y=5))
        ],
    )
    resultado = build_pieza(pieza)
    assert any("solo barrenos" in o for o in resultado.features_omitidos)


def test_barreno_lateral_en_base_circular_se_omite():
    pieza = Pieza(
        pieza="disco",
        material=Material(nombre="Aluminio 6061"),
        dimensiones=Dimensiones(forma_base=FormaBase.CIRCULAR, diametro_mm=50, espesor_mm=10),
        features=[Feature(id="f1", tipo=TipoFeature.BARRENO, diametro_mm=6, cara="lateral_izquierda", posicion=Posicion2D(x=5, y=5))],
    )
    resultado = build_pieza(pieza)
    assert any("base rectangular" in o for o in resultado.features_omitidos)


def test_ranura_tiene_extremos_realmente_redondeados_no_rectangulo():
    """The removed volume must match a real stadium shape (rectangle +
    two half-circle caps), not a sharp-cornered rectangle - the exact
    complaint that drove this fix. A sharp rectangle of the same
    largo x ancho would remove strictly MORE material than a slot with
    rounded ends (the rounded caps leave the corner material in place),
    so this is a real, discriminating geometric check, not a smoke test.
    """
    ancho, largo, espesor = 10.0, 30.0, 8.0
    pieza = Pieza(
        pieza="placa_con_ranura",
        material=Material(nombre="Aluminio 6061"),
        dimensiones=Dimensiones(forma_base=FormaBase.RECTANGULAR, largo_mm=100, ancho_mm=60, espesor_mm=espesor),
        features=[Feature(id="r1", tipo=TipoFeature.RANURA, ancho_mm=ancho, largo_mm=largo, posicion=Posicion2D(x=50, y=30))],
    )
    resultado = build_pieza(pieza)
    assert resultado.advertencias == []  # the old "modeled as a rectangle" warning must be GONE for a real slot
    props = calcular_propiedades(resultado.solido)

    volumen_base = 100 * 60 * espesor
    volumen_removido = volumen_base - props["volumen_mm3"]

    largo_recto = largo - ancho
    area_stadium = largo_recto * ancho + math.pi * (ancho / 2) ** 2
    volumen_esperado_stadium = area_stadium * espesor
    volumen_rectangulo_afilado = largo * ancho * espesor

    assert volumen_removido == pytest.approx(volumen_esperado_stadium, rel=0.01)
    assert volumen_removido < volumen_rectangulo_afilado - 1.0  # meaningfully less - the rounded corners are real


def test_ranura_muy_corta_cae_a_rectangulo_con_advertencia():
    """slot2D can't build a slot shorter than it is wide (degenerate case,
    not something a real end mill would call a "slot" anyway) - must fall
    back safely with an honest warning, never silently produce nothing.
    """
    pieza = Pieza(
        pieza="placa",
        material=Material(nombre="Aluminio 6061"),
        dimensiones=Dimensiones(forma_base=FormaBase.RECTANGULAR, largo_mm=100, ancho_mm=60, espesor_mm=10),
        features=[Feature(id="r1", tipo=TipoFeature.RANURA, ancho_mm=10, largo_mm=8, posicion=Posicion2D(x=50, y=30))],
    )
    resultado = build_pieza(pieza)
    assert any("no se puede construir como ranura" in a for a in resultado.advertencias)


def test_redondeo_con_posicion_afecta_solo_esa_esquina():
    """Exactly the real gap reported on PM-001: a plano calling out R10 at
    ONE specific corner (not all four) needs that one corner rounded and
    the rest left sharp - the old behavior (no `posicion` support) could
    only do all-or-nothing.
    """
    perfil = [
        Posicion2D(x=0, y=0), Posicion2D(x=30, y=0), Posicion2D(x=30, y=10),
        Posicion2D(x=90, y=10), Posicion2D(x=90, y=0), Posicion2D(x=120, y=0),
        Posicion2D(x=120, y=65), Posicion2D(x=80, y=65), Posicion2D(x=80, y=80),
        Posicion2D(x=40, y=80), Posicion2D(x=40, y=65), Posicion2D(x=0, y=65),
    ]
    pieza = Pieza(
        pieza="PM-001",
        material=Material(nombre="Aluminio 6061"),
        dimensiones=Dimensiones(forma_base=FormaBase.POLIGONAL, espesor_mm=15, puntos_perfil_mm=perfil),
        features=[Feature(id="r10", tipo=TipoFeature.REDONDEO, radio_mm=10, posicion=Posicion2D(x=40, y=80))],
    )
    resultado = build_pieza(pieza)
    assert resultado.advertencias == []

    props = calcular_propiedades(resultado.solido)
    # Footprint = 120x65 main body (7800) - 60x10 bottom notch (600) + 40x15 top tab (600) = 7800mm2 (shoelace-verified).
    volumen_base = 7800 * 15
    # A 90-degree R10 corner cut removes r^2*(1 - pi/4) of area, times espesor -
    # hand-verified directly against cadquery before writing this test.
    volumen_esperado_removido_por_el_redondeo = (10.0**2) * (1 - math.pi / 4) * 15
    volumen_removido_real = volumen_base - props["volumen_mm3"]
    assert volumen_removido_real == pytest.approx(volumen_esperado_removido_por_el_redondeo, rel=0.01)


def _placa_con_chaflan_compuesto(pasante: bool = True) -> Pieza:
    segmentos = [
        SegmentoChaflanCompuesto(profundidad_mm=5.0, angulo_grados=20.0),
        SegmentoChaflanCompuesto(profundidad_mm=5.0, angulo_grados=20.0),
        SegmentoChaflanCompuesto(profundidad_mm=12.0, angulo_grados=30.0),
    ]
    return Pieza(
        pieza="placa_con_avellanado",
        material=Material(nombre="Aluminio 6061"),
        dimensiones=Dimensiones(forma_base=FormaBase.RECTANGULAR, largo_mm=80, ancho_mm=80, espesor_mm=44),
        features=[
            Feature(
                id="f1", tipo=TipoFeature.BARRENO, diametro_mm=22, pasante=pasante,
                posicion=Posicion2D(x=40, y=40), chaflanes_compuestos=segmentos,
            )
        ],
    )


def test_chaflan_compuesto_no_crashea_y_no_se_omite():
    """Found missing on a real client part (a DeAcero shear blade): each
    hole has a 3-stage countersink at BOTH ends (Detalle B/Detalle C on
    the plano), not a simple single-angle chamfer - the geometry engine
    had no way to represent that at all before this feature existed.
    """
    resultado = build_pieza(_placa_con_chaflan_compuesto())
    assert resultado.advertencias == []
    assert resultado.features_omitidos == []


def test_chaflan_compuesto_remueve_mas_volumen_que_el_barreno_liso():
    con_chaflan = calcular_propiedades(build_pieza(_placa_con_chaflan_compuesto()).solido)["volumen_mm3"]

    pieza_lisa = _placa_con_chaflan_compuesto()
    pieza_lisa.features[0].chaflanes_compuestos = None
    sin_chaflan = calcular_propiedades(build_pieza(pieza_lisa).solido)["volumen_mm3"]

    assert con_chaflan < sin_chaflan


def test_chaflan_compuesto_radio_en_la_cara_coincide_con_la_geometria_de_los_conos():
    """Cross-check the volume actually removed against the exact analytic
    volume of the 3 stacked frustums (both ends, since pasante) plus the
    straight bore in between - if the cone radii/heights were wired up
    wrong this is what would catch it, not just "some volume disappeared".
    """
    import math as m

    pieza = _placa_con_chaflan_compuesto()
    resultado = build_pieza(pieza)
    props = calcular_propiedades(resultado.solido)
    volumen_removido = 80 * 80 * 44 - props["volumen_mm3"]

    r_bore = 11.0
    segmentos = [(5.0, 20.0), (5.0, 20.0), (12.0, 30.0)]
    radios = [r_bore]
    for prof, ang in reversed(segmentos):
        radios.append(radios[-1] + prof * m.tan(m.radians(ang / 2)))
    radios.reverse()

    def volumen_frustum(r1, r2, h):
        return (m.pi * h / 3) * (r1**2 + r1 * r2 + r2**2)

    volumen_un_extremo = sum(volumen_frustum(radios[i], radios[i + 1], prof) for i, (prof, _) in enumerate(segmentos))
    profundidad_recta = 44 - 2 * sum(prof for prof, _ in segmentos)
    volumen_recto = m.pi * r_bore**2 * profundidad_recta
    volumen_esperado = 2 * volumen_un_extremo + volumen_recto

    assert volumen_removido == pytest.approx(volumen_esperado, rel=0.02)


def test_chaflan_compuesto_no_pasante_solo_corta_una_cara():
    resultado_pasante = build_pieza(_placa_con_chaflan_compuesto(pasante=True))
    resultado_ciego = build_pieza(_placa_con_chaflan_compuesto(pasante=False))
    vol_pasante = calcular_propiedades(resultado_pasante.solido)["volumen_mm3"]
    vol_ciego = calcular_propiedades(resultado_ciego.solido)["volumen_mm3"]
    assert vol_ciego > vol_pasante  # the blind version is missing the mirrored bottom cut + rest of the through-bore
