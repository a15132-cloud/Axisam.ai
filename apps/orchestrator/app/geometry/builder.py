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
- features on lateral_* faces
- feature.tipo = escalon, perfil_exterior (need explicit boundary geometry)
Everything unsupported surfaces as a clear warning or error so a human
catches it at the Capa 6 model-preview checkpoint - never modeled blindly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import cadquery as cq

from app.schemas.piece import Feature, FormaBase, Pieza, Posicion2D, TipoFeature

MARGEN_CORTE_MM = 1.0
PROFUNDIDAD_CIEGA_DEFAULT_FRACCION = 0.5


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

        if f.cara and f.cara.startswith("lateral"):
            omitidos.append(f"{f.tipo.value} (id={f.id or '?'}): caras laterales no soportadas aun")
            continue

        if f.patron_incompleto:
            advertencias.append(
                f"{f.tipo.value} (id={f.id or '?'}): cantidad={f.cantidad} pero solo se conoce "
                f"{len(f.lista_posiciones())} posicion(es) - revisa el patron completo antes de aprobar el modelo."
            )

        posiciones = f.lista_posiciones()
        if not posiciones:
            omitidos.append(f"{f.tipo.value} (id={f.id or '?'}): sin posicion conocida, no se pudo modelar")
            continue

        for pos in posiciones:
            if f.tipo in (TipoFeature.BARRENO, TipoFeature.BARRENO_ROSCADO):
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
