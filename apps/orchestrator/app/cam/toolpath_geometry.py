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
