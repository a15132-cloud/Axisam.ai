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
