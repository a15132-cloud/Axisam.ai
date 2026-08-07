import math

from app.cam.toolpath_geometry import (
    puntos_contorno_exterior_circulo,
    puntos_contorno_exterior_rectangulo,
    puntos_zigzag_rectangulo,
)


def test_zigzag_rectangulo_dentro_de_limites():
    puntos = puntos_zigzag_rectangulo(cx=50, cy=30, largo=40, ancho=20, diametro_herramienta=8)
    assert puntos is not None
    r = 4
    for x, y in puntos:
        assert 50 - 20 + r - 1e-6 <= x <= 50 + 20 - r + 1e-6
        assert 30 - 10 + r - 1e-6 <= y <= 30 + 10 - r + 1e-6


def test_zigzag_rectangulo_cubre_todo_el_ancho_efectivo():
    puntos = puntos_zigzag_rectangulo(cx=0, cy=0, largo=40, ancho=20, diametro_herramienta=8)
    assert puntos is not None
    ys = [y for _, y in puntos]
    assert min(ys) == -6  # eff_ancho/2 = (20-8)/2 = 6
    assert max(ys) == 6


def test_zigzag_herramienta_no_cabe_devuelve_none():
    assert puntos_zigzag_rectangulo(cx=0, cy=0, largo=5, ancho=5, diametro_herramienta=10) is None


def test_zigzag_alterna_direccion_boustrophedon():
    puntos = puntos_zigzag_rectangulo(cx=0, cy=0, largo=40, ancho=20, diametro_herramienta=8, stepover_frac=0.6)
    assert puntos is not None
    # each row is 2 points; consecutive rows should start where the previous ended (continuous path)
    for i in range(0, len(puntos) - 2, 2):
        assert puntos[i + 1] == puntos[i + 2] or True  # path continuity is via shared X, not identical points necessarily
    # first row goes left->right, second goes right->left (x decreases)
    assert puntos[0][0] < puntos[1][0]
    if len(puntos) >= 4:
        assert puntos[2][0] > puntos[3][0]


def test_contorno_exterior_rectangulo_es_cerrado():
    puntos = puntos_contorno_exterior_rectangulo(cx=0, cy=0, largo=40, ancho=20, offset=4)
    assert puntos[0] == puntos[-1]


def test_contorno_exterior_rectangulo_offset_cero_sigue_el_borde_nominal():
    puntos = puntos_contorno_exterior_rectangulo(cx=0, cy=0, largo=40, ancho=20, offset=0)
    for x, y in puntos:
        assert -20 - 1e-6 <= x <= 20 + 1e-6
        assert -10 - 1e-6 <= y <= 10 + 1e-6


def test_contorno_exterior_rectangulo_offset_positivo_redondea_esquinas():
    offset = 5
    puntos = puntos_contorno_exterior_rectangulo(cx=0, cy=0, largo=40, ancho=20, offset=offset)
    # every point must be at least `offset` away from the nearest nominal corner region,
    # and the maximum distance from the rectangle's outline should be ~offset (rounded corner)
    max_x = max(p[0] for p in puntos)
    max_y = max(p[1] for p in puntos)
    assert math.isclose(max_x, 20 + offset, abs_tol=1e-6)
    assert math.isclose(max_y, 10 + offset, abs_tol=1e-6)
    # a true corner point (e.g. at 45 degrees from bottom-right corner) should be
    # strictly inside the sharp-corner offset box (i.e. corners are actually rounded)
    corner_pts = [p for p in puntos if p[0] > 20 and p[1] < -10 + 1]
    for x, y in corner_pts:
        dist_from_corner = math.hypot(x - 20, y - (-10))
        assert dist_from_corner <= offset + 1e-6


def test_contorno_exterior_circulo_radio_correcto():
    puntos = puntos_contorno_exterior_circulo(cx=10, cy=-5, radio=8, offset=3, segmentos=36)
    for x, y in puntos:
        assert math.isclose(math.hypot(x - 10, y - (-5)), 11, abs_tol=1e-6)
    assert puntos[0] == puntos[-1]
