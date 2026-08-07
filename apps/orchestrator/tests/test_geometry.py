from pathlib import Path

import pytest

from app.geometry.builder import GeometryBuildError, build_pieza
from app.geometry.export import calcular_propiedades, exportar_step, exportar_stl
from app.schemas.piece import Dimensiones, Feature, FormaBase, Material, Pieza, Posicion2D, TipoFeature


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
    pieza.dimensiones.forma_base = FormaBase.POLIGONAL
    with pytest.raises(GeometryBuildError):
        build_pieza(pieza)


def test_feature_no_soportado_se_omite_no_crashea():
    pieza = _placa_soporte()
    pieza.features.append(Feature(id="f3", tipo=TipoFeature.ESCALON, ancho_mm=10, largo_mm=10, profundidad_mm=2))
    resultado = build_pieza(pieza)
    assert any("escalon" in o for o in resultado.features_omitidos)


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
