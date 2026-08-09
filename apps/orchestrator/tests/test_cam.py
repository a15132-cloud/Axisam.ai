import math

from app.cam.gcode import generar_codigo_g
from app.cam.planner import planear_trayectoria
from app.cam.simulate import simular_maquinado
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


def test_simular_maquinado_resumen():
    pieza = _placa_soporte()
    plan = planear_trayectoria(pieza)
    resumen = simular_maquinado(pieza, plan)
    assert resumen.numero_operaciones == 2
    assert resumen.es_simulacion is True
    assert any("ESTIMACION" in w for w in resumen.advertencias)
