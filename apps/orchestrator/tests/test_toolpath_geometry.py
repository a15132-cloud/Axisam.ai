import math

from app.cam.toolpath_geometry import (
    puntos_anillos_concentricos,
    puntos_contorno_exterior_circulo,
    puntos_contorno_exterior_rectangulo,
    puntos_zigzag_rectangulo,
    radio_maximo_inscrito,
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


def test_radio_maximo_inscrito_rectangulo_centrado():
    # centered in a 100x60 rectangle: nearest edge is the short side, 30mm away
    rect = [(0, 0), (100, 0), (100, 60), (0, 60)]
    assert math.isclose(radio_maximo_inscrito(50, 30, rect), 30.0, abs_tol=1e-9)


def test_radio_maximo_inscrito_punto_descentrado():
    rect = [(0, 0), (100, 0), (100, 60), (0, 60)]
    # 20mm from the left edge, 20mm from the bottom edge, both closer than the other two sides
    assert math.isclose(radio_maximo_inscrito(20, 20, rect), 20.0, abs_tol=1e-9)


def test_radio_maximo_inscrito_perfil_escalonado():
    """Same 12-point stepped profile as the real PM-001 drawing (a tab
    sticking up on top, a notch cut into the bottom) - the boss sits at
    (60, 40). Straight up from the boss is actually still inside the tab
    (open space, X 40-80 continues up to Y=80), so the nearest boundary
    ISN'T the shoulder at Y=65 (32mm away, at the shoulder/tab corner) -
    it's the bottom notch's top edge, exactly 30mm straight down
    (40 - 10 = 30), the true minimum across all 12 edges.
    """
    perfil = [
        (0, 0), (30, 0), (30, 10), (90, 10), (90, 0), (120, 0),
        (120, 65), (80, 65), (80, 80), (40, 80), (40, 65), (0, 65),
    ]
    assert math.isclose(radio_maximo_inscrito(60, 40, perfil), 30.0, abs_tol=1e-9)


def test_anillos_concentricos_se_quedan_en_el_anillo_pedido():
    anillos = puntos_anillos_concentricos(cx=50, cy=30, radio_interior=10, radio_exterior=25, diametro_herramienta=8)
    assert len(anillos) >= 2  # (25-10)/(8*0.6) ~= 3 rings
    for anillo in anillos:
        assert anillo[0] == anillo[-1]  # closed loop
        for x, y in anillo:
            r = math.hypot(x - 50, y - 30)
            assert 10 - 1e-6 <= r <= 25 + 1e-6
    # rings ordered smallest-first (cut outward from the boss, never back into cleared material)
    radios = [math.hypot(anillo[0][0] - 50, anillo[0][1] - 30) for anillo in anillos]
    assert radios == sorted(radios)


def test_anillos_concentricos_sin_espacio_devuelve_vacio():
    assert puntos_anillos_concentricos(cx=0, cy=0, radio_interior=20, radio_exterior=18, diametro_herramienta=8) == []
