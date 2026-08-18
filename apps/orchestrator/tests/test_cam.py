import math

import pytest

from app.cam.gcode import generar_codigo_g
from app.cam.planner import planear_trayectoria
from app.cam.simulate import simular_maquinado
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
            Feature(id="f2", tipo=TipoFeature.CAJERA, ancho_mm=20, largo_mm=20, profundidad_mm=3, posicion=Posicion2D(x=50, y=30)),
        ],
    )


def test_planear_trayectoria_placa_soporte():
    plan = planear_trayectoria(_placa_soporte())
    assert len(plan.operaciones) == 2
    assert plan.postprocesador["controlador"] == "haas"
    assert plan.plan.tiempo_estimado_min and plan.plan.tiempo_estimado_min > 0


def test_generar_codigo_g_barreno_y_cajera_ambos_con_movimiento_real():
    pieza = _placa_soporte()
    plan = planear_trayectoria(pieza)
    resultado = generar_codigo_g(pieza, plan)

    assert "SIMULACION" in resultado.contenido
    assert "NO CARGAR EN LA MAQUINA" in resultado.contenido
    assert "M30" in resultado.contenido
    assert "G81" in resultado.contenido or "G83" in resultado.contenido  # real drilling cycle
    assert "G1 X" in resultado.contenido and "G1 Y" not in resultado.contenido  # G1 lines carry both X and Y together
    assert resultado.operaciones_con_movimiento_real == 2
    assert resultado.operaciones_solo_planeadas == 0
    assert "TRAYECTORIA NO GENERADA" not in resultado.contenido


def test_barreno_pasante_a_traves_de_saliente_llega_a_la_profundidad_correcta():
    """Regression test for a real bug found while testing against an
    actual customer drawing: a through-hole was planned using just the
    base plate espesor, coming up short wherever a boss (saliente) sat on
    top of it - the drilled depth must clear the boss's added height too,
    or the hole simply doesn't go all the way through the real part.
    """
    pieza = Pieza(
        pieza="placa_con_boss",
        material=Material(nombre="Aluminio 6061"),
        dimensiones=Dimensiones(forma_base=FormaBase.RECTANGULAR, largo_mm=100, ancho_mm=60, espesor_mm=10),
        features=[
            Feature(id="boss", tipo=TipoFeature.SALIENTE, diametro_mm=30, profundidad_mm=5, posicion=Posicion2D(x=50, y=30)),
            Feature(id="hoyo", tipo=TipoFeature.BARRENO, diametro_mm=10, pasante=True, posicion=Posicion2D(x=50, y=30)),
        ],
    )
    plan = planear_trayectoria(pieza)
    resultado = generar_codigo_g(pieza, plan)

    assert "Z-15.000" in resultado.contenido  # 10mm base + 5mm boss, not just the base
    assert "Z-10.000" not in resultado.contenido


def test_barreno_lejos_del_saliente_no_se_ve_afectado():
    """The fix above must be position-aware, not a blanket "always add the
    tallest boss on the part" - a hole nowhere near any boss should still
    use the plain base espesor.
    """
    pieza = Pieza(
        pieza="placa_con_boss",
        material=Material(nombre="Aluminio 6061"),
        dimensiones=Dimensiones(forma_base=FormaBase.RECTANGULAR, largo_mm=100, ancho_mm=60, espesor_mm=10),
        features=[
            Feature(id="boss", tipo=TipoFeature.SALIENTE, diametro_mm=30, profundidad_mm=5, posicion=Posicion2D(x=50, y=30)),
            Feature(id="hoyo_lejano", tipo=TipoFeature.BARRENO, diametro_mm=6, pasante=True, posicion=Posicion2D(x=10, y=10)),
        ],
    )
    plan = planear_trayectoria(pieza)
    resultado = generar_codigo_g(pieza, plan)

    assert "Z-10.000" in resultado.contenido
    assert "Z-15.000" not in resultado.contenido


def test_saliente_genera_trayectoria_real_de_careado_alrededor():
    """End-to-end: a boss on a rectangular plate must produce real G1
    facing motion (not a "TRAYECTORIA NO GENERADA" placeholder), staying
    within the part boundary and outside the boss itself.
    """
    pieza = Pieza(
        pieza="placa_con_boss",
        material=Material(nombre="Aluminio 6061"),
        dimensiones=Dimensiones(forma_base=FormaBase.RECTANGULAR, largo_mm=100, ancho_mm=60, espesor_mm=10),
        features=[Feature(id="boss", tipo=TipoFeature.SALIENTE, diametro_mm=20, profundidad_mm=5, posicion=Posicion2D(x=50, y=30))],
    )
    plan = planear_trayectoria(pieza)
    resultado = generar_codigo_g(pieza, plan)

    assert resultado.operaciones_con_movimiento_real == 1
    assert resultado.operaciones_solo_planeadas == 0
    assert "TRAYECTORIA NO GENERADA" not in resultado.contenido

    lineas = [l for l in resultado.contenido.splitlines() if l.startswith("G1 X")]
    assert lineas, "se esperaba movimiento G1 real de careado"
    radio_boss = 10.0
    for linea in lineas:
        x = float(linea.split("X")[1].split(" ")[0])
        y = float(linea.split("Y")[1].split(" ")[0])
        r = math.hypot(x - 50, y - 30)
        assert r > radio_boss  # never cuts into the boss itself
        assert 0.0 <= x <= 100.0 and 0.0 <= y <= 60.0  # stays on the real part


def test_cajera_toolpath_se_mantiene_dentro_de_los_limites():
    pieza = _placa_soporte()
    plan = planear_trayectoria(pieza)
    resultado = generar_codigo_g(pieza, plan)

    lineas = [l for l in resultado.contenido.splitlines() if l.startswith("G1 X")]
    assert lineas, "se esperaban movimientos G1 de la cajera"
    for linea in lineas:
        x = float(linea.split("X")[1].split(" ")[0])
        y = float(linea.split("Y")[1].split(" ")[0])
        # cajera de 20x20 en (50,30): el centro de la herramienta nunca debe
        # salir del rectangulo nominal de la cajera
        assert 40.0 <= x <= 60.0
        assert 20.0 <= y <= 40.0


def test_cajera_entra_en_rampa_no_en_plunge_recto():
    """A real customer question ("if I run this on the CNC, will it just
    break the tool?") exposed that every Z descent here was a straight
    G1 Z-only plunge - most end mills aren't rated to cut on-center like a
    drill. Every descending move must now also move in XY (a real angled
    ramp), and the tool must actually reach full depth before the pocket's
    own perimeter pass starts (not stop short at some intermediate Z).
    """
    pieza = _placa_soporte()
    plan = planear_trayectoria(pieza)
    resultado = generar_codigo_g(pieza, plan)

    lineas = resultado.contenido.splitlines()
    inicio = next(i for i, l in enumerate(lineas) if "CAJERA" in l)
    fin = next(i for i in range(inicio + 1, len(lineas)) if lineas[i].startswith("("))
    bloque = lineas[inicio:fin]

    descensos = [l for l in bloque if l.startswith("G1") and " Z" in l]
    assert descensos, "se esperaban movimientos de descenso en la cajera"
    for linea in descensos:
        assert "X" in linea and "Y" in linea, f"descenso sin movimiento XY (plunge recto): {linea}"

    # La cajera de 3mm de profundidad (una sola pasada) debe llegar exacto a Z-3.000
    profundidades = [float(l.split("Z")[1].split(" ")[0]) for l in descensos]
    assert min(profundidades) == pytest.approx(-3.0, abs=0.01)


def test_advertencias_features_cercanas_detecta_barrenos_muy_juntos():
    """Real, if bounded (2D footprint-level, not full 3D collision),
    gouge-risk check: two features positioned close enough that only their
    combined TOOL clearance (not their own nominal outlines) overlaps must
    be flagged before the human approves the plan, not discovered by the
    machine crashing into already-cut material.
    """
    pieza = Pieza(
        pieza="placa_barrenos_juntos",
        material=Material(nombre="Aluminio 6061"),
        dimensiones=Dimensiones(forma_base=FormaBase.RECTANGULAR, largo_mm=100, ancho_mm=60, espesor_mm=10),
        features=[
            Feature(id="h1", tipo=TipoFeature.BARRENO, diametro_mm=10, posicion=Posicion2D(x=30, y=30)),
            Feature(id="h2", tipo=TipoFeature.BARRENO, diametro_mm=10, posicion=Posicion2D(x=38, y=30)),
            Feature(id="h3", tipo=TipoFeature.BARRENO, diametro_mm=8, posicion=Posicion2D(x=80, y=30)),
        ],
    )
    plan = planear_trayectoria(pieza)

    choques = [a for a in plan.plan.advertencias if "POSIBLE CHOQUE" in a]
    assert len(choques) == 1
    assert "h1" in choques[0] and "h2" in choques[0]
    assert "h3" not in choques[0]


def test_advertencias_features_cercanas_no_marca_patron_bien_espaciado():
    pieza = _placa_soporte()  # f1 es un patron de 4 barrenos de 8mm, separados 70/30mm
    plan = planear_trayectoria(pieza)
    assert not any("POSIBLE CHOQUE" in a for a in plan.plan.advertencias)


def test_perfil_exterior_genera_contorno_real_redondeado_en_las_esquinas():
    pieza = Pieza(
        pieza="placa",
        material=Material(nombre="Aluminio 6061"),
        dimensiones=Dimensiones(forma_base=FormaBase.RECTANGULAR, largo_mm=100, ancho_mm=60, espesor_mm=10),
        features=[Feature(id="perfil", tipo=TipoFeature.PERFIL_EXTERIOR, profundidad_mm=10)],
    )
    plan = planear_trayectoria(pieza)
    resultado = generar_codigo_g(pieza, plan)

    assert resultado.operaciones_con_movimiento_real == 1
    assert resultado.operaciones_solo_planeadas == 0
    lineas_g1 = [l for l in resultado.contenido.splitlines() if l.startswith("G1 X")]
    assert lineas_g1
    # el contorno debe salirse del rectangulo nominal (offset hacia afuera = radio de herramienta)
    max_x = max(float(l.split("X")[1].split(" ")[0]) for l in lineas_g1)
    assert max_x > 100.0


def test_escalon_genera_trayectoria_real_a_lo_largo_del_borde():
    """Found missing on a real client part (a DeAcero shear blade): a
    relief running the full length of one edge. escalon used to always be
    a placeholder (not enough geometry in the JSON to route a toolpath) -
    now that cara/ancho_mm/profundidad_mm fully describe the edge strip,
    it gets real G1 motion like cajera/ranura.
    """
    pieza = _placa_soporte()
    pieza.features.append(Feature(id="f3", tipo=TipoFeature.ESCALON, cara="lateral_frontal", ancho_mm=10, profundidad_mm=2))
    plan = planear_trayectoria(pieza)
    resultado = generar_codigo_g(pieza, plan)

    assert "TRAYECTORIA NO GENERADA" not in resultado.contenido
    assert resultado.operaciones_con_movimiento_real == 3  # barreno + cajera (both already in _placa_soporte) + escalon
    assert resultado.operaciones_solo_planeadas == 0


def test_escalon_sin_profundidad_sigue_siendo_placeholder_honesto():
    """No profundidad_mm anywhere in the drawing means no cut in the
    STEP/STL model (see app/geometry/builder.py) - the G-code must refuse
    to invent motion here too, rather than fall back to the generic
    "guess 50% of espesor" rule every other blind feature gets, which
    would leave the G-code cutting material the solid model never removed.
    """
    pieza = _placa_soporte()
    pieza.features.append(Feature(id="f3", tipo=TipoFeature.ESCALON, cara="lateral_frontal", ancho_mm=10, profundidad_mm=None))
    plan = planear_trayectoria(pieza)
    resultado = generar_codigo_g(pieza, plan)

    assert "TRAYECTORIA NO GENERADA" in resultado.contenido
    assert "tampoco se modelo en el solido" in resultado.contenido


def test_cajera_con_herramienta_mas_grande_que_el_bolsillo_no_genera_movimiento_falso():
    pieza = Pieza(
        pieza="placa",
        material=Material(nombre="Aluminio 6061"),
        dimensiones=Dimensiones(forma_base=FormaBase.RECTANGULAR, largo_mm=100, ancho_mm=60, espesor_mm=10),
        features=[Feature(id="f1", tipo=TipoFeature.CAJERA, ancho_mm=2, largo_mm=2, profundidad_mm=1, posicion=Posicion2D(x=50, y=30))],
    )
    plan = planear_trayectoria(pieza)
    resultado = generar_codigo_g(pieza, plan)

    assert "NO CABE" in resultado.contenido
    assert resultado.operaciones_con_movimiento_real == 0
    assert resultado.operaciones_solo_planeadas == 1


def test_operacion_sin_movimiento_no_hace_cambio_de_herramienta_falso():
    """A real rough edge found while testing against a client drawing: a
    feature with nothing to cut still staged the machine for it anyway -
    tool change, spindle start, coolant on/off around a cut that never
    happens. A machinist reading the file would see the machine "get
    ready" and then do nothing. This applies to escalon, cajera and
    saliente alike whenever a whole operation ends up with zero real
    movement - only the identifying comment and the reason should appear,
    no M6/M3/M8/M9 wrapped around empty air.
    """
    pieza = Pieza(
        pieza="placa",
        material=Material(nombre="Aluminio 6061"),
        dimensiones=Dimensiones(forma_base=FormaBase.RECTANGULAR, largo_mm=100, ancho_mm=60, espesor_mm=10),
        features=[Feature(id="f1", tipo=TipoFeature.ESCALON, cara="lateral_frontal", ancho_mm=8, profundidad_mm=None)],
    )
    plan = planear_trayectoria(pieza)
    resultado = generar_codigo_g(pieza, plan)

    assert "TRAYECTORIA NO GENERADA" in resultado.contenido
    assert "M6" not in resultado.contenido
    assert "M3 " not in resultado.contenido
    assert "M8" not in resultado.contenido


def test_encabezado_avisa_de_operaciones_sin_cortar_y_no_confunde_las_reales():
    """A real client concern this must never fail on: if ANY operation in
    the file has no real toolpath, that must be impossible to miss - not
    something buried mid-file a machinist could scroll past. The summary
    goes at the very top, before even the postprocessor/date comments.

    This also regression-tests a bug caught before it shipped: the drilled
    barreno comes FIRST in this piece and always has real motion, but it
    never explicitly set the loop's hubo_movimiento flag - so with the
    escalon (no motion) processed second, a naive read could have carried
    the previous iteration's flag over and mislabeled the drilling
    operation as "sin cortar" too. It must not appear in the summary.
    """
    pieza = Pieza(
        pieza="placa",
        material=Material(nombre="Aluminio 6061"),
        dimensiones=Dimensiones(forma_base=FormaBase.RECTANGULAR, largo_mm=100, ancho_mm=60, espesor_mm=10),
        features=[
            Feature(id="hoyo_real", tipo=TipoFeature.BARRENO, diametro_mm=8, posicion=Posicion2D(x=50, y=30)),
            Feature(id="relieve_sin_profundidad", tipo=TipoFeature.ESCALON, cara="lateral_frontal", ancho_mm=8, profundidad_mm=None),
        ],
    )
    plan = planear_trayectoria(pieza)
    resultado = generar_codigo_g(pieza, plan)

    primeras_lineas = resultado.contenido.splitlines()[:10]
    encabezado = "\n".join(primeras_lineas)
    assert "ATENCION" in encabezado
    assert "relieve_sin_profundidad" in encabezado
    assert "hoyo_real" not in encabezado  # the real, fully-machined operation must not show up as pending
    assert resultado.operaciones_con_movimiento_real == 1
    assert resultado.operaciones_solo_planeadas == 1


def test_ciclo_taladrado_no_se_cancela_entre_barrenos():
    """G0 between repeated positions would cancel the G81/G83 modal cycle
    (same modal group), turning holes 2..N into unmachined rapid moves."""
    pieza = _placa_soporte()
    plan = planear_trayectoria(pieza)
    resultado = generar_codigo_g(pieza, plan)

    lineas = resultado.contenido.splitlines()
    idx_ciclo = next(i for i, l in enumerate(lineas) if l.startswith(("G81", "G83")))
    idx_g80 = next(i for i, l in enumerate(lineas) if l.strip() == "G80")
    for linea in lineas[idx_ciclo + 1 : idx_g80]:
        assert not linea.startswith("G0"), f"G0 cancela el ciclo de taladrado modal: {linea!r}"


def test_barreno_roscado_avisa_que_solo_genero_el_pretaladro():
    """Regression test for a real bug found in this audit: barreno_roscado
    was routed through the exact same drilling block as a plain barreno,
    which only ever emits a pilot-hole cycle (G81/G83) - there was no G84/
    tapping cycle anywhere in this codebase, and no warning said so either.
    The file looked complete (real motion, no red flags) while silently
    never actually cutting the thread. Must now be loudly disclosed, both
    in the .nc comments and in the structured advertencias the UI surfaces.
    """
    pieza = Pieza(
        pieza="placa_con_rosca",
        material=Material(nombre="Aluminio 6061"),
        dimensiones=Dimensiones(forma_base=FormaBase.RECTANGULAR, largo_mm=100, ancho_mm=60, espesor_mm=10),
        features=[
            Feature(id="f1", tipo=TipoFeature.BARRENO_ROSCADO, diametro_mm=6, rosca="M6x1.0", posicion=Posicion2D(x=50, y=30), pasante=True),
        ],
    )
    plan = planear_trayectoria(pieza)
    resultado = generar_codigo_g(pieza, plan)

    # This must already be visible in the TOOLPATH PLAN's own advertencias -
    # what SimulacionCard shows BEFORE the human approves - not just in the
    # final G-code, which only gets generated AFTER aprobacion_final is
    # already True (see app/tools/handlers.py). Otherwise a human approves
    # believing the part is fully machined and only finds out afterward.
    assert any("pretaladro" in w for w in plan.plan.advertencias)

    assert "SOLO genero el pretaladro" in resultado.contenido
    assert "falta el ciclo de machuelo" in resultado.contenido
    assert any("pretaladro" in a and "f1" in a for a in resultado.advertencias)
    # The pilot hole itself IS real motion - not the same failure mode as
    # "nothing was cut", so it still counts and must NOT show up in the
    # sin-cortar ATENCION block (that would misdescribe what's wrong here).
    assert resultado.operaciones_con_movimiento_real == 1
    assert "OPERACION(ES) SIN CORTAR" not in resultado.contenido


def test_chaflan_compuesto_avisa_que_no_tiene_trayectoria_generada():
    """Regression test for a real bug found in this audit: chaflanes_compuestos
    (the multi-stage countersink used on the real DeAcero part earlier this
    project) is cut correctly into the STEP/STL by the geometry engine, but
    had ZERO references anywhere in app/cam/ - the G-code just drilled the
    straight bore and said nothing about the countersink at all. A part built
    from this file would come out with an unmachined countersink and no
    warning telling anyone that happened.
    """
    pieza = Pieza(
        pieza="placa_con_avellanado",
        material=Material(nombre="Aluminio 6061"),
        dimensiones=Dimensiones(forma_base=FormaBase.RECTANGULAR, largo_mm=100, ancho_mm=60, espesor_mm=20),
        features=[
            Feature(
                id="f1",
                tipo=TipoFeature.BARRENO,
                diametro_mm=10,
                pasante=True,
                posicion=Posicion2D(x=50, y=30),
                chaflanes_compuestos=[
                    SegmentoChaflanCompuesto(profundidad_mm=3, angulo_grados=20),
                    SegmentoChaflanCompuesto(profundidad_mm=5, angulo_grados=30),
                ],
            ),
        ],
    )
    plan = planear_trayectoria(pieza)
    resultado = generar_codigo_g(pieza, plan)

    # Same visibility requirement as the barreno_roscado case above: this
    # must show up before approval, in the plan's own advertencias.
    assert any("avellanado" in w for w in plan.plan.advertencias)

    assert "avellanado no tiene" in resultado.contenido
    assert any("avellanado" in a and "f1" in a for a in resultado.advertencias)
    # El barreno recto si es movimiento real - el hueco es especificamente
    # el avellanado, no la operacion completa.
    assert resultado.operaciones_con_movimiento_real == 1


def test_barreno_lateral_no_genera_ciclo_recto_en_z():
    """Regression test for a real bug found in this audit: a barreno drilled
    into a side face (feature.cara = lateral_*, see app.geometry.builder's
    CARAS_LATERALES) was falling into the same code path as a normal top-down
    hole, which only ever emits a straight -Z canned cycle (G81/G83) at the
    hole's (x, y). That's real-looking G-code cutting on the wrong axis, in
    the wrong place - worse than not generating it. A lateral barreno must be
    left as an explicit "not generated" placeholder instead, exactly like any
    other feature this generator can't safely route.
    """
    pieza = Pieza(
        pieza="placa_con_barreno_lateral",
        material=Material(nombre="Aluminio 6061"),
        dimensiones=Dimensiones(forma_base=FormaBase.RECTANGULAR, largo_mm=100, ancho_mm=60, espesor_mm=10),
        features=[
            Feature(id="f1", tipo=TipoFeature.BARRENO, diametro_mm=6, cara="lateral_frontal", posicion=Posicion2D(x=50, y=5)),
        ],
    )
    plan = planear_trayectoria(pieza)
    resultado = generar_codigo_g(pieza, plan)

    # Same visibility requirement as the other two gaps above: this must
    # show up before approval, in the plan's own advertencias.
    assert any("4to eje" in w for w in plan.plan.advertencias)

    # No ACTUAL canned-cycle command line was emitted (the strategy
    # description text legitimately mentions "G81/G83" as prose, so check
    # real G-code lines specifically, same style as
    # test_ciclo_taladrado_no_se_cancela_entre_barrenos).
    assert not any(l.startswith(("G81", "G83")) for l in resultado.contenido.splitlines())
    assert "TRAYECTORIA NO GENERADA" in resultado.contenido
    assert "lateral_frontal" in resultado.contenido
    assert resultado.operaciones_con_movimiento_real == 0
    assert resultado.operaciones_solo_planeadas == 1
    assert "id=f1" in resultado.contenido  # surfaced with its own feature id, not silently dropped


def test_barreno_normal_no_lateral_sigue_generando_ciclo_real():
    """Guard against the lateral check being too broad and swallowing
    ordinary top-face barrenos (cara=None or "superior")."""
    pieza = _placa_soporte()
    plan = planear_trayectoria(pieza)
    resultado = generar_codigo_g(pieza, plan)
    assert "G81" in resultado.contenido or "G83" in resultado.contenido


def test_simular_maquinado_resumen():
    pieza = _placa_soporte()
    plan = planear_trayectoria(pieza)
    resumen = simular_maquinado(pieza, plan)
    assert resumen.numero_operaciones == 2
    assert resumen.es_simulacion is True
    assert any("ESTIMACION" in w for w in resumen.advertencias)
