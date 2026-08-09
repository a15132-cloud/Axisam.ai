"""Pure geometry functions for 2.5D toolpaths - no G-code, no I/O, easy to
unit-test in isolation. This is what turns cajera/perfil_exterior from a
"not generated" placeholder into real, computed cutter-center motion.

Deliberate simplifications, stated once here instead of scattered as
comments: corners are approximated with short line segments rather than
G2/G3 arcs (fewer ways to get a direction/IJ sign wrong - a straight line
approximation is unambiguous by construction), plunge entries are
straight (a real CAM post would ramp or pre-drill), and there is no
gouge/collision checking between simultaneous features. All of that is
still true of the eventual real-Mastercam output too in terms of what the
*plan* recommends - it's the actual cutter path that's newly real here.
"""

from __future__ import annotations

import math

from app.schemas.piece import FormaBase, Pieza

Punto = tuple[float, float]


def puntos_zigzag_rectangulo(
    cx: float, cy: float, largo: float, ancho: float, diametro_herramienta: float, stepover_frac: float = 0.6
) -> list[Punto] | None:
    """Boustrophedon (zigzag) clearing of a rectangular pocket, inset by the
    tool radius on all sides (the tool center never reaches the nominal
    wall - a real wall-finish pass would follow, not modeled here).
    Returns None if the tool does not fit inside the pocket at all.
    """
    r = diametro_herramienta / 2
    eff_largo = largo - 2 * r
    eff_ancho = ancho - 2 * r
    if eff_largo <= 0 or eff_ancho <= 0:
        return None

    stepover = max(diametro_herramienta * stepover_frac, 0.05)
    x0, x1 = cx - eff_largo / 2, cx + eff_largo / 2
    y0, y1 = cy - eff_ancho / 2, cy + eff_ancho / 2

    n_filas = max(1, math.ceil(eff_ancho / stepover) + 1)
    ys = [cy] if n_filas == 1 else [y0 + i * (eff_ancho / (n_filas - 1)) for i in range(n_filas)]

    puntos: list[Punto] = []
    izquierda_a_derecha = True
    for y in ys:
        if izquierda_a_derecha:
            puntos.append((x0, y))
            puntos.append((x1, y))
        else:
            puntos.append((x1, y))
            puntos.append((x0, y))
        izquierda_a_derecha = not izquierda_a_derecha
    return puntos


def puntos_contorno_exterior_rectangulo(
    cx: float, cy: float, largo: float, ancho: float, offset: float, segmentos_esquina: int = 6
) -> list[Punto]:
    """Tool-center path around a rectangle's boundary, offset outward by
    `offset` (typically the tool radius for a real profile cut, or 0 to
    trace the nominal edge for a form tool like a corner-round/chamfer
    mill, whose own profile - not the offset - creates the fillet/chamfer).
    Positive offset rounds the convex corners (correct Minkowski-sum
    behavior for milling around the OUTSIDE of a shape); each corner is
    approximated by `segmentos_esquina` short line segments. Closed path
    (first point == last point).
    """
    L2, W2, r = largo / 2, ancho / 2, offset
    # (corner_center_x, corner_center_y, start_angle_deg, end_angle_deg), traversed CCW
    esquinas = [
        (cx + L2, cy - W2, -90, 0),
        (cx + L2, cy + W2, 0, 90),
        (cx - L2, cy + W2, 90, 180),
        (cx - L2, cy - W2, 180, 270),
    ]
    puntos: list[Punto] = []
    for (ccx, ccy, a0, a1) in esquinas:
        pasos = segmentos_esquina if r > 1e-6 else 1
        for i in range(pasos):
            a = math.radians(a0 + (a1 - a0) * i / pasos)
            puntos.append((ccx + r * math.cos(a), ccy + r * math.sin(a)))
    puntos.append(puntos[0])
    return puntos


def puntos_contorno_exterior_circulo(cx: float, cy: float, radio: float, offset: float, segmentos: int = 48) -> list[Punto]:
    """Tool-center path around a circular boundary, offset outward by
    `offset`, linearized into `segmentos` points (closed path)."""
    r = radio + offset
    puntos = [(cx + r * math.cos(2 * math.pi * i / segmentos), cy + r * math.sin(2 * math.pi * i / segmentos)) for i in range(segmentos)]
    puntos.append(puntos[0])  # exact closure - recomputing cos/sin(2*pi) is not bit-identical to i=0
    return puntos


def _distancia_punto_a_segmento(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def radio_maximo_inscrito(cx: float, cy: float, vertices: list[Punto]) -> float:
    """Largest circle centered at (cx, cy) that stays fully inside the
    closed polygon `vertices` - the minimum distance from the center to
    any edge. Correct whenever (cx, cy) is actually inside the polygon,
    which is always true here (a boss/saliente center is inside the part
    outline by construction). Used to find how far a facing operation can
    spread around a boss WITHOUT cutting outside the real part boundary -
    a defined, computed limit instead of an arbitrary guess at "how big
    should the facing area be."
    """
    n = len(vertices)
    return min(
        _distancia_punto_a_segmento(cx, cy, vertices[i][0], vertices[i][1], vertices[(i + 1) % n][0], vertices[(i + 1) % n][1])
        for i in range(n)
    )


def vertices_contorno_nominal_pieza(pieza: Pieza) -> list[Punto] | None:
    """Raw (un-offset) boundary vertices of the part's own outline - used
    to find how far a facing pass can spread before it would cut outside
    the real part (see radio_maximo_inscrito), NOT to generate a
    tool-center path directly (a real cutting path needs a tool-radius
    offset inward from this). None for shapes not handled here (a boss on
    a revolucion part isn't something this engine builds in the first
    place, so this is a narrow, rarely-hit gap).
    """
    d = pieza.dimensiones
    if d.forma_base == FormaBase.POLIGONAL and d.puntos_perfil_mm:
        return [(p.x, p.y) for p in d.puntos_perfil_mm]
    if d.forma_base == FormaBase.RECTANGULAR and d.largo_mm and d.ancho_mm:
        return [(0.0, 0.0), (d.largo_mm, 0.0), (d.largo_mm, d.ancho_mm), (0.0, d.ancho_mm)]
    return None


def puntos_anillos_concentricos(
    cx: float, cy: float, radio_interior: float, radio_exterior: float, diametro_herramienta: float, segmentos: int = 48
) -> list[list[Punto]]:
    """Concentric closed circular tool-center passes clearing the annular
    area between radio_interior and radio_exterior (e.g. facing the
    material around a boss to leave it standing proud). Returned smallest
    ring first, so cutting proceeds outward from the boss - never
    re-entering material already cleared at a larger radius after a
    smaller one. Empty list if there's no room for even one pass.
    """
    if radio_exterior <= radio_interior:
        return []
    stepover = max(diametro_herramienta * 0.6, 0.1)
    n_anillos = max(1, math.ceil((radio_exterior - radio_interior) / stepover))
    radios = [radio_interior + i * (radio_exterior - radio_interior) / n_anillos for i in range(1, n_anillos + 1)]
    anillos = []
    for r in radios:
        anillo = [(cx + r * math.cos(2 * math.pi * i / segmentos), cy + r * math.sin(2 * math.pi * i / segmentos)) for i in range(segmentos)]
        anillo.append(anillo[0])
        anillos.append(anillo)
    return anillos
