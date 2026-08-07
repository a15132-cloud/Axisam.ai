"""Capa 4 (SolidWorks side) - real geometry bridge.

Builds an actual solid model from a confirmed `Pieza` using the OpenCascade
kernel (via cadquery) and exports genuine STEP/STL files the user can open
directly in SolidWorks or Mastercam today.

This stands in for `crear_boceto_solidworks` / `extruir_solidworks` /
`agregar_feature_solidworks` while there is no live SolidWorks COM server
to call. The geometry is real, not a placeholder - only the *origin* of
the geometry differs from the target architecture (OpenCascade kernel here
vs. native SolidWorks kernel via COM later). When the Windows SolidWorks
server is available, this module can be swapped for one that drives the
COM API while keeping the exact same `build_pieza` -> STEP/STL contract.

Deliberately unsupported (raise GeometryBuildError instead of guessing):
- forma_base = poligonal / revolucion (no profile geometry in the schema)
- pockets/slots on lateral_* faces (barrenos are supported there - see
  CARAS_LATERALES - but a rectangular cut needs a second in-plane axis
  convention this schema doesn't carry yet)
- feature.tipo = escalon, perfil_exterior (need explicit boundary geometry)
Everything unsupported surfaces as a clear warning or error so a human
catches it at the Capa 6 model-preview checkpoint - never modeled blindly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import cadquery as cq

from app.schemas.piece import Dimensiones, Feature, FormaBase, Pieza, Posicion2D, TipoFeature

MARGEN_CORTE_MM = 1.0
PROFUNDIDAD_CIEGA_DEFAULT_FRACCION = 0.5

# Side-face drilling convention: for a rectangular part spanning
# X in [0, largo], Y in [0, ancho], Z in [0, espesor], each lateral face
# gets its own 2D coordinate frame - feature.posicion.x runs along the
# face's width axis, feature.posicion.y runs up the part's height (Z) -
# so the same (x, y) meaning ("distance across", "distance up") applies
# no matter which of the four side faces a hole is on. `origen` maps that
# 2D position to a 3D world point on the face; `direccion` is the drilling
# axis (always pointing INTO the part); `longitud_max` is the full-through
# depth along that axis.
CARAS_LATERALES = {
    "lateral_izquierda": {  # X = 0 face
        "origen": lambda pos, d: (0.0, pos.x, pos.y),
        "direccion": (1.0, 0.0, 0.0),
        "longitud_max": lambda d: d.largo_mm,
    },
    "lateral_derecha": {  # X = largo face
        "origen": lambda pos, d: (d.largo_mm, pos.x, pos.y),
        "direccion": (-1.0, 0.0, 0.0),
        "longitud_max": lambda d: d.largo_mm,
    },
    "lateral_frontal": {  # Y = 0 face
        "origen": lambda pos, d: (pos.x, 0.0, pos.y),
        "direccion": (0.0, 1.0, 0.0),
        "longitud_max": lambda d: d.ancho_mm,
    },
    "lateral_posterior": {  # Y = ancho face
        "origen": lambda pos, d: (pos.x, d.ancho_mm, pos.y),
        "direccion": (0.0, -1.0, 0.0),
        "longitud_max": lambda d: d.ancho_mm,
    },
}


class GeometryBuildError(Exception):
    pass


@dataclass
class BuildResult:
    solido: cq.Workplane
    advertencias: list[str] = field(default_factory=list)
    features_omitidos: list[str] = field(default_factory=list)


def _workplane_en(x: float, y: float, z: float) -> cq.Workplane:
    return cq.Workplane("XY").workplane(offset=z).center(x, y)


def _base_rectangular(largo: float, ancho: float, espesor: float) -> cq.Workplane:
    return cq.Workplane("XY").rect(largo, ancho, centered=False).extrude(espesor)


def _base_circular(diametro: float, espesor: float) -> cq.Workplane:
    return cq.Workplane("XY").circle(diametro / 2).extrude(espesor)


def _rango_z(feature: Feature, espesor: float) -> tuple[float, float]:
    """Returns (z_inicio_workplane, distancia_extrude) for the cutting tool."""
    if feature.pasante:
        return -MARGEN_CORTE_MM, espesor + 2 * MARGEN_CORTE_MM
    profundidad = feature.profundidad_mm or espesor * PROFUNDIDAD_CIEGA_DEFAULT_FRACCION
    if feature.cara == "inferior":
        return 0.0, profundidad
    return espesor, -profundidad  # superior (default): cut downward from top face


def _cortar_barreno(solido: cq.Workplane, feature: Feature, pos: Posicion2D, espesor: float) -> cq.Workplane:
    z0, dz = _rango_z(feature, espesor)
    diametro = feature.diametro_mm or 5.0
    herramienta = _workplane_en(pos.x, pos.y, z0).circle(diametro / 2).extrude(dz)
    return solido.cut(herramienta)


def _cortar_barreno_lateral(
    solido: cq.Workplane, feature: Feature, pos: Posicion2D, dims: Dimensiones, cara: str
) -> cq.Workplane:
    config = CARAS_LATERALES[cara]
    ox, oy, oz = config["origen"](pos, dims)
    dx, dy, dz = config["direccion"]
    longitud_total = config["longitud_max"](dims)
    profundidad = longitud_total if feature.pasante else (feature.profundidad_mm or longitud_total * PROFUNDIDAD_CIEGA_DEFAULT_FRACCION)

    radio = (feature.diametro_mm or 5.0) / 2
    # Start the cylinder MARGEN_CORTE_MM outside the face so the boolean
    # cut has clean overlap at the surface, regardless of face orientation.
    punto_inicio = cq.Vector(ox - dx * MARGEN_CORTE_MM, oy - dy * MARGEN_CORTE_MM, oz - dz * MARGEN_CORTE_MM)
    direccion = cq.Vector(dx, dy, dz)
    herramienta_shape = cq.Solid.makeCylinder(radio, profundidad + MARGEN_CORTE_MM, pnt=punto_inicio, dir=direccion)
    herramienta = cq.Workplane(obj=herramienta_shape)
    return solido.cut(herramienta)


def _cortar_rectangulo(
    solido: cq.Workplane, feature: Feature, pos: Posicion2D, espesor: float, ancho: float, largo: float
) -> cq.Workplane:
    z0, dz = _rango_z(feature, espesor)
    herramienta = _workplane_en(pos.x, pos.y, z0).rect(largo, ancho).extrude(dz)
    return solido.cut(herramienta)


def _aplicar_redondeos_chaflanes(solido: cq.Workplane, features: list[Feature], advertencias: list[str]) -> cq.Workplane:
    """Must run before any hole/pocket cuts: only then are the vertical
    edges of the base ("|Z") exactly the outer corners, unambiguous to
    select. Cutting first would add hole-wall edges to the same selector.
    """
    for f in features:
        if f.tipo == TipoFeature.REDONDEO:
            radio = f.radio_mm or 3.0
            try:
                solido = solido.edges("|Z").fillet(radio)
            except Exception as exc:  # OCCT fillet can fail on tight geometry
                advertencias.append(f"No se pudo aplicar redondeo R{radio}mm en las esquinas: {exc}")
        elif f.tipo == TipoFeature.CHAFLAN:
            distancia = f.radio_mm or 2.0
            if f.angulo_grados and not math.isclose(f.angulo_grados, 45.0, abs_tol=1.0):
                advertencias.append(
                    f"Chaflan con angulo {f.angulo_grados} grados solicitado; el motor automatico solo "
                    "soporta chaflan simetrico 45 grados en esta fase - se aplico a 45 grados."
                )
            try:
                solido = solido.edges("|Z").chamfer(distancia)
            except Exception as exc:
                advertencias.append(f"No se pudo aplicar chaflan {distancia}mm en las esquinas: {exc}")
    return solido


def build_pieza(pieza: Pieza) -> BuildResult:
    dims = pieza.dimensiones
    advertencias: list[str] = []
    omitidos: list[str] = []

    if dims.forma_base == FormaBase.RECTANGULAR:
        solido = _base_rectangular(dims.largo_mm, dims.ancho_mm, dims.espesor_mm)
    elif dims.forma_base == FormaBase.CIRCULAR:
        solido = _base_circular(dims.diametro_mm, dims.espesor_mm)
    else:
        raise GeometryBuildError(
            f"forma_base='{dims.forma_base.value}' requiere geometria de perfil que no esta en el JSON "
            "extraido del plano. Este tipo de pieza necesita modelado asistido en SolidWorks por ahora."
        )

    # Corner fillets/chamfers first (see docstring on why order matters).
    corner_features = [f for f in pieza.features if f.tipo in (TipoFeature.REDONDEO, TipoFeature.CHAFLAN)]
    if corner_features and dims.forma_base != FormaBase.RECTANGULAR:
        for f in corner_features:
            omitidos.append(f"{f.tipo.value} (id={f.id or '?'}): solo soportado en piezas de base rectangular")
    elif corner_features:
        solido = _aplicar_redondeos_chaflanes(solido, corner_features, advertencias)

    for f in pieza.features:
        if f.tipo in (TipoFeature.REDONDEO, TipoFeature.CHAFLAN):
            continue  # already handled above

        if f.patron_incompleto:
            advertencias.append(
                f"{f.tipo.value} (id={f.id or '?'}): cantidad={f.cantidad} pero solo se conoce "
                f"{len(f.lista_posiciones())} posicion(es) - revisa el patron completo antes de aprobar el modelo."
            )

        posiciones = f.lista_posiciones()
        if not posiciones:
            omitidos.append(f"{f.tipo.value} (id={f.id or '?'}): sin posicion conocida, no se pudo modelar")
            continue

        es_lateral = bool(f.cara and f.cara.startswith("lateral"))
        if es_lateral and f.cara not in CARAS_LATERALES:
            omitidos.append(
                f"{f.tipo.value} (id={f.id or '?'}): cara '{f.cara}' no reconocida - usar lateral_izquierda, "
                "lateral_derecha, lateral_frontal o lateral_posterior"
            )
            continue
        if es_lateral and dims.forma_base != FormaBase.RECTANGULAR:
            omitidos.append(f"{f.tipo.value} (id={f.id or '?'}): caras laterales solo soportadas en piezas de base rectangular")
            continue
        if es_lateral and f.tipo not in (TipoFeature.BARRENO, TipoFeature.BARRENO_ROSCADO):
            omitidos.append(
                f"{f.tipo.value} (id={f.id or '?'}) en cara '{f.cara}': solo barrenos estan soportados en caras "
                "laterales por ahora - modelar manualmente en SolidWorks."
            )
            continue

        for pos in posiciones:
            if f.tipo in (TipoFeature.BARRENO, TipoFeature.BARRENO_ROSCADO):
                if es_lateral:
                    solido = _cortar_barreno_lateral(solido, f, pos, dims, f.cara)
                else:
                    solido = _cortar_barreno(solido, f, pos, dims.espesor_mm)
                if f.tipo == TipoFeature.BARRENO_ROSCADO:
                    advertencias.append(
                        f"barreno_roscado {f.rosca or ''} (id={f.id or '?'}): modelado como barreno liso "
                        "(rosca cosmetica) - la geometria de la helice no se genera en esta fase."
                    )
            elif f.tipo == TipoFeature.CAJERA:
                ancho = f.ancho_mm or 10.0
                largo = f.largo_mm or 10.0
                solido = _cortar_rectangulo(solido, f, pos, dims.espesor_mm, ancho, largo)
            elif f.tipo == TipoFeature.RANURA:
                ancho = f.ancho_mm or 5.0
                largo = f.largo_mm or 20.0
                solido = _cortar_rectangulo(solido, f, pos, dims.espesor_mm, ancho, largo)
                advertencias.append(
                    f"ranura (id={f.id or '?'}): modelada como rectangulo - los extremos redondeados "
                    "por la fresa no estan representados en esta fase."
                )
            elif f.tipo in (TipoFeature.ESCALON, TipoFeature.PERFIL_EXTERIOR):
                omitidos.append(
                    f"{f.tipo.value} (id={f.id or '?'}): requiere geometria de contorno que no esta en el "
                    "JSON extraido - modelar manualmente en SolidWorks por ahora."
                )
            else:
                omitidos.append(f"{f.tipo.value} (id={f.id or '?'}): tipo de feature no reconocido por el motor")

    return BuildResult(solido=solido, advertencias=advertencias, features_omitidos=omitidos)
