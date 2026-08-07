"""Capa 5 - Base de conocimiento de manufactura.

Explicit decision tables over YAML data, not ML. Given a material and a
feature, decide: which tool, what cutting parameters, what strategy, and
via which postprocessor. Every function here is a pure lookup/formula so
a machinist can audit or override any single decision.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from app.schemas.piece import Feature, Material, TipoFeature

DATA_DIR = Path(__file__).parent / "data"


class MaterialNoEncontrado(Exception):
    pass


@dataclass
class HerramientaSeleccionada:
    tipo: str
    diametro_mm: float
    flautas: int | None = None
    descripcion: str = ""
    exacta: bool = True


@dataclass
class ParametrosCorte:
    vc_m_min: float
    rpm: float
    avance_mm_min: float
    avance_por_diente_mm: float
    refrigerante: str
    advertencias: list[str] = field(default_factory=list)


@dataclass
class OperacionRecomendada:
    feature_id: str | None
    estrategia: str
    herramienta: HerramientaSeleccionada
    parametros: ParametrosCorte
    profundidad_pasada_mm: float | None
    notas: list[str] = field(default_factory=list)


@lru_cache(maxsize=1)
def _cargar_yaml(nombre: str) -> dict:
    with open(DATA_DIR / nombre, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _materiales() -> dict:
    return _cargar_yaml("materials.yaml")["materiales"]


def _herramientas() -> dict:
    return _cargar_yaml("tools.yaml")


def _postprocesadores() -> dict:
    return _cargar_yaml("postprocessors.yaml")


def normalizar_clave_material(nombre: str) -> str:
    return (
        nombre.strip()
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
        .replace(".", "")
    )


def buscar_material(material: Material) -> dict:
    materiales = _materiales()
    clave = normalizar_clave_material(material.nombre)
    if clave in materiales:
        return {"clave": clave, **materiales[clave]}
    # fallback: match by substring on nombre_display (handles slight naming drift)
    for k, v in materiales.items():
        if clave in normalizar_clave_material(v["nombre_display"]):
            return {"clave": k, **v}
    raise MaterialNoEncontrado(
        f"Material '{material.nombre}' no esta en la base de conocimiento. "
        f"Materiales disponibles: {', '.join(sorted(materiales))}"
    )


def seleccionar_broca(diametro_mm: float) -> HerramientaSeleccionada:
    brocas = sorted(_herramientas()["brocas"], key=lambda b: b["diametro_mm"])
    exacta = next((b for b in brocas if math.isclose(b["diametro_mm"], diametro_mm, abs_tol=0.05)), None)
    if exacta:
        return HerramientaSeleccionada(tipo="broca", diametro_mm=exacta["diametro_mm"], descripcion=f"Broca {exacta['diametro_mm']} mm")
    mayor = next((b for b in brocas if b["diametro_mm"] > diametro_mm), None)
    if mayor:
        return HerramientaSeleccionada(
            tipo="broca", diametro_mm=mayor["diametro_mm"], descripcion=f"Broca {mayor['diametro_mm']} mm (mas cercana disponible)", exacta=False
        )
    mas_grande = brocas[-1]
    return HerramientaSeleccionada(
        tipo="broca", diametro_mm=mas_grande["diametro_mm"], descripcion="Fuera de rango de catalogo - broca mas grande disponible", exacta=False
    )


def seleccionar_fresa(diametro_max_mm: float, tipo: str = "fresas_planas_carburo") -> HerramientaSeleccionada:
    fresas = sorted(_herramientas()[tipo], key=lambda f: f["diametro_mm"], reverse=True)
    # pick the largest cutter that still fits inside the feature (never wider than the pocket/slot)
    candidata = next((f for f in fresas if f["diametro_mm"] <= diametro_max_mm), fresas[-1])
    exacta = candidata["diametro_mm"] <= diametro_max_mm
    return HerramientaSeleccionada(
        tipo=tipo,
        diametro_mm=candidata["diametro_mm"],
        flautas=candidata.get("flautas"),
        descripcion=f"Fresa {candidata['diametro_mm']} mm, {candidata.get('flautas', '?')} flautas",
        exacta=exacta,
    )


def buscar_machuelo(rosca: str) -> dict | None:
    for m in _herramientas()["machuelos"]:
        if m["rosca"].replace(" ", "").lower() == rosca.replace(" ", "").lower():
            return m
    return None


def calcular_parametros_corte(
    material_info: dict,
    diametro_herramienta_mm: float,
    tipo_herramienta: str,
    flautas: int | None = None,
) -> ParametrosCorte:
    vc = material_info["vc_recomendada_m_min"]
    rpm = (vc * 1000) / (math.pi * diametro_herramienta_mm)
    avance_diente_key = "fresa_carburo" if "fresa" in tipo_herramienta else "broca"
    avance_por_diente = material_info["avance_por_diente_mm"].get(avance_diente_key, 0.05)
    dientes_efectivos = flautas or (1 if tipo_herramienta == "broca" else 2)
    avance_mm_min = rpm * dientes_efectivos * avance_por_diente

    advertencias: list[str] = []
    if rpm > 12000:
        advertencias.append(f"RPM calculado ({rpm:.0f}) es alto - verificar limite del husillo de la maquina")
    if material_info.get("validado_por") is None:
        advertencias.append(
            f"Parametros de corte para '{material_info['nombre_display']}' son valores de referencia (seed data) "
            "sin validar por un maquinista - confirmar antes de maquinar."
        )

    return ParametrosCorte(
        vc_m_min=vc,
        rpm=round(rpm, 0),
        avance_mm_min=round(avance_mm_min, 1),
        avance_por_diente_mm=avance_por_diente,
        refrigerante=material_info.get("refrigerante", "recomendado"),
        advertencias=advertencias,
    )


# --- Estrategia por tipo de feature (tabla de decision explicita) ---

_ESTRATEGIA_POR_FEATURE: dict[TipoFeature, str] = {
    TipoFeature.BARRENO: "Taladrado con ciclo fijo (G81/G83 segun profundidad)",
    TipoFeature.BARRENO_ROSCADO: "Taladrado de pretaladro + machuelo rigido (G84)",
    TipoFeature.CAJERA: "Desbaste en espiral/zigzag + acabado de contorno perimetral",
    TipoFeature.PERFIL_EXTERIOR: "Contorneado perimetral en niveles Z, entrada tangencial",
    TipoFeature.CHAFLAN: "Fresa de chaflan en contorno de la arista indicada",
    TipoFeature.REDONDEO: "Fresa de bola o chaflan segun radio, contorno de la arista",
    TipoFeature.RANURA: "Fresado de ranura en pasadas multiples (ancho > diametro fresa)",
    TipoFeature.ESCALON: "Fresado de escalon por niveles, desbaste + acabado",
}


def seleccionar_estrategia(feature: Feature) -> str:
    return _ESTRATEGIA_POR_FEATURE.get(feature.tipo, "Estrategia no definida - revisar manualmente")


def planear_operacion(feature: Feature, material: Material, espesor_pieza_mm: float) -> OperacionRecomendada:
    """The core Capa 5 decision: for one feature, decide tool + cutting
    params + strategy. This is what generar_trayectoria_mastercam calls
    per feature.
    """
    info_material = buscar_material(material)
    estrategia = seleccionar_estrategia(feature)
    notas: list[str] = []

    if feature.tipo == TipoFeature.BARRENO_ROSCADO and feature.rosca:
        machuelo = buscar_machuelo(feature.rosca)
        diametro_broca = machuelo["diametro_pretaladro_mm"] if machuelo else (feature.diametro_mm or 5.0) * 0.85
        if not machuelo:
            notas.append(f"Rosca '{feature.rosca}' no esta en catalogo de machuelos - diametro de pretaladro estimado")
        herramienta = seleccionar_broca(diametro_broca)
        parametros = calcular_parametros_corte(info_material, herramienta.diametro_mm, "broca")
    elif feature.tipo == TipoFeature.BARRENO:
        diametro = feature.diametro_mm or 5.0
        herramienta = seleccionar_broca(diametro)
        parametros = calcular_parametros_corte(info_material, herramienta.diametro_mm, "broca")
    elif feature.tipo in (TipoFeature.CAJERA, TipoFeature.RANURA, TipoFeature.ESCALON):
        ancho_disponible = min(v for v in (feature.ancho_mm, feature.largo_mm, feature.radio_mm) if v) if any(
            (feature.ancho_mm, feature.largo_mm, feature.radio_mm)
        ) else 10.0
        herramienta = seleccionar_fresa(ancho_disponible * 0.8)
        parametros = calcular_parametros_corte(info_material, herramienta.diametro_mm, herramienta.tipo, herramienta.flautas)
    elif feature.tipo == TipoFeature.CHAFLAN:
        herramienta = seleccionar_fresa(20.0, tipo="fresas_chaflan")
        parametros = calcular_parametros_corte(info_material, herramienta.diametro_mm, herramienta.tipo)
    elif feature.tipo == TipoFeature.REDONDEO:
        radio = feature.radio_mm or 3.0
        herramienta = seleccionar_fresa(radio * 2, tipo="fresas_bola_carburo")
        parametros = calcular_parametros_corte(info_material, herramienta.diametro_mm, herramienta.tipo, herramienta.flautas)
    else:  # PERFIL_EXTERIOR / default
        herramienta = seleccionar_fresa(min(espesor_pieza_mm * 2, 12.0))
        parametros = calcular_parametros_corte(info_material, herramienta.diametro_mm, herramienta.tipo, herramienta.flautas)

    if not herramienta.exacta:
        notas.append(f"No hay herramienta exacta en catalogo para este feature - se selecciono {herramienta.descripcion}")

    profundidad = feature.profundidad_mm or (espesor_pieza_mm if feature.pasante else None)
    max_pasada = min(herramienta.diametro_mm * 0.5, 3.0) if herramienta.tipo != "broca" else profundidad

    return OperacionRecomendada(
        feature_id=feature.id,
        estrategia=estrategia,
        herramienta=herramienta,
        parametros=parametros,
        profundidad_pasada_mm=max_pasada,
        notas=notas,
    )


def obtener_postprocesador(nombre: str | None = None) -> dict:
    pps = _postprocesadores()
    clave = nombre or pps["default"]
    if clave not in pps["postprocesadores"]:
        disponibles = ", ".join(pps["postprocesadores"])
        raise ValueError(f"Postprocesador '{clave}' no reconocido. Disponibles: {disponibles}")
    return {"clave": clave, **pps["postprocesadores"][clave]}


def listar_materiales() -> list[dict]:
    return [{"clave": k, **v} for k, v in _materiales().items()]


def listar_postprocesadores() -> list[dict]:
    pps = _postprocesadores()
    return [{"clave": k, **v} for k, v in pps["postprocesadores"].items()]
