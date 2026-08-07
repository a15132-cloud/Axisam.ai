"""Structured contract for a machined part, extracted from a plano (Capa 3)
and consumed by every downstream layer (geometry, knowledge base, CAM).

This is the one JSON shape the whole pipeline agrees on. Vision extraction
produces it, the human confirms/edits it, geometry building consumes it,
and the CAM planner consumes it again. Nothing downstream should need to
re-parse a drawing or re-derive geometry from prose.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class TipoMaquinado(str, Enum):
    FRESADO = "fresado"
    TORNEADO = "torneado"
    FRESADO_MULTIEJE = "fresado_multieje"


class TipoFeature(str, Enum):
    BARRENO = "barreno"
    BARRENO_ROSCADO = "barreno_roscado"
    CAJERA = "cajera"
    PERFIL_EXTERIOR = "perfil_exterior"
    CHAFLAN = "chaflan"
    REDONDEO = "redondeo"
    RANURA = "ranura"
    ESCALON = "escalon"


class FormaBase(str, Enum):
    """Silhouette used to build the base solid via extrusion / revolution."""

    RECTANGULAR = "rectangular"
    CIRCULAR = "circular"
    POLIGONAL = "poligonal"
    REVOLUCION = "revolucion"


class Posicion2D(BaseModel):
    x: float
    y: float


class SimboloGDT(BaseModel):
    """A single GD&T callout per ISO 1101 / ASME Y14.5."""

    tipo: str = Field(
        description=(
            "planitud, paralelismo, perpendicularidad, posicion, "
            "concentricidad, circularidad, cilindricidad, perfil, etc."
        )
    )
    valor_mm: float
    datum_referencia: Optional[str] = Field(
        default=None, description="Datum letter(s) referenced, e.g. 'A' or 'A|B'"
    )
    aplica_a: Optional[str] = Field(
        default=None, description="Feature id or description this callout applies to"
    )


class Feature(BaseModel):
    id: Optional[str] = None
    tipo: TipoFeature
    diametro_mm: Optional[float] = None
    profundidad_mm: Optional[float] = None
    ancho_mm: Optional[float] = None
    largo_mm: Optional[float] = None
    radio_mm: Optional[float] = None
    angulo_grados: Optional[float] = None
    posicion: Optional[Posicion2D] = None
    posiciones: Optional[list[Posicion2D]] = Field(
        default=None,
        description="Para patrones (varios barrenos identicos): una posicion por instancia. Tiene prioridad sobre 'posicion'.",
    )
    cara: Optional[str] = Field(
        default="superior", description="Cara de la pieza donde se ubica: superior, inferior, lateral_N"
    )
    pasante: bool = Field(default=True, description="True si el barreno/ranura atraviesa la pieza")
    cantidad: int = Field(default=1, description="Numero de instancias de este feature (patron)")
    tolerancia_mm: Optional[float] = None
    rosca: Optional[str] = Field(default=None, description="Especificacion de rosca, p.ej. 'M8x1.25'")
    gdt: list[SimboloGDT] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_shape_params(self) -> "Feature":
        if self.tipo in (TipoFeature.BARRENO, TipoFeature.BARRENO_ROSCADO) and self.diametro_mm is None:
            raise ValueError(f"feature {self.tipo} requiere diametro_mm")
        return self

    def lista_posiciones(self) -> list[Posicion2D]:
        """Instancias con posicion conocida. Si cantidad > 1 pero solo hay
        una posicion (sin patron explicito), devuelve esa unica posicion:
        el llamador debe advertir que el patron completo no se modelo.
        """
        if self.posiciones:
            return self.posiciones
        if self.posicion:
            return [self.posicion]
        return []

    @property
    def patron_incompleto(self) -> bool:
        return self.cantidad > 1 and len(self.lista_posiciones()) < self.cantidad


class Dimensiones(BaseModel):
    forma_base: FormaBase = FormaBase.RECTANGULAR
    largo_mm: Optional[float] = None
    ancho_mm: Optional[float] = None
    diametro_mm: Optional[float] = None
    espesor_mm: float
    longitud_mm: Optional[float] = Field(
        default=None, description="Para piezas de revolucion (torneado): longitud sobre el eje"
    )

    @model_validator(mode="after")
    def _validate_base_dims(self) -> "Dimensiones":
        if self.forma_base == FormaBase.RECTANGULAR and (self.largo_mm is None or self.ancho_mm is None):
            raise ValueError("forma_base=rectangular requiere largo_mm y ancho_mm")
        if self.forma_base == FormaBase.CIRCULAR and self.diametro_mm is None:
            raise ValueError("forma_base=circular requiere diametro_mm")
        return self


class ToleranciaGeneral(BaseModel):
    valor_mm: float = 0.1
    norma: Optional[str] = Field(default="ISO 2768-m", description="Norma de tolerancia general aplicada")


class Material(BaseModel):
    nombre: str = Field(description="p.ej. 'Aluminio 6061', 'Acero 1045', 'Acero inoxidable 304'")
    designacion: Optional[str] = Field(default=None, description="UNS/AISI/SAE si se identifica")
    dureza: Optional[str] = None


class ExtraccionMeta(BaseModel):
    """Confidence + provenance info so a human knows what to double check."""

    confianza_global: float = Field(ge=0.0, le=1.0, default=0.0)
    campos_baja_confianza: list[str] = Field(default_factory=list)
    notas: Optional[str] = None
    archivo_origen: Optional[str] = None


class Pieza(BaseModel):
    pieza: str = Field(description="Nombre/identificador de la pieza")
    tipo_maquinado: TipoMaquinado = TipoMaquinado.FRESADO
    material: Material
    dimensiones: Dimensiones
    tolerancia_general: ToleranciaGeneral = Field(default_factory=ToleranciaGeneral)
    features: list[Feature] = Field(default_factory=list)
    acabado_superficial: Optional[str] = Field(default=None, description="p.ej. 'Ra 3.2', 'N/A'")
    cantidad: int = 1
    unidades: str = "mm"
    extraccion: ExtraccionMeta = Field(default_factory=ExtraccionMeta)

    model_config = {
        "json_schema_extra": {
            "example": {
                "pieza": "placa_soporte",
                "tipo_maquinado": "fresado",
                "material": {"nombre": "Aluminio 6061"},
                "dimensiones": {
                    "forma_base": "rectangular",
                    "largo_mm": 100,
                    "ancho_mm": 60,
                    "espesor_mm": 10,
                },
                "tolerancia_general": {"valor_mm": 0.05, "norma": "ISO 2768-f"},
                "features": [
                    {
                        "tipo": "barreno",
                        "diametro_mm": 8,
                        "posicion": {"x": 50, "y": 30},
                        "tolerancia_mm": 0.05,
                        "cantidad": 4,
                    }
                ],
                "acabado_superficial": "Ra 3.2",
                "cantidad": 1,
            }
        }
    }
