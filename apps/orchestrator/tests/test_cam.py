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


def test_escalon_sigue_siendo_placeholder_honesto():
    """escalon no tiene suficiente geometria en el JSON para una trayectoria
    real (que arista, que direccion) - debe seguir marcado como pendiente."""
    pieza = _placa_soporte()
    pieza.features.append(
        Feature(id="f3", tipo=TipoFeature.ESCALON, ancho_mm=10, largo_mm=10, profundidad_mm=2, posicion=Posicion2D(x=10, y=10))
    )
    plan = planear_trayectoria(pieza)
    resultado = generar_codigo_g(pieza, plan)

    assert "TRAYECTORIA NO GENERADA" in resultado.contenido
    assert resultado.operaciones_solo_planeadas == 1
    assert any("quedaron solo planeadas" in w for w in resultado.advertencias)


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
