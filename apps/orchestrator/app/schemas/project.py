"""Project/session state: the pipeline stage machine (Capa 6) and the
artifacts produced at each stage. One Proyecto = one part going through
plano -> modelo 3D -> trayectorias -> codigo G -> aprobacion.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.piece import Pieza


class Etapa(str, Enum):
    PLANO_SUBIDO = "plano_subido"
    EXTRAYENDO = "extrayendo"
    ESPERANDO_CONFIRMACION_EXTRACCION = "esperando_confirmacion_extraccion"
    MODELANDO = "modelando"
    ESPERANDO_CONFIRMACION_MODELO = "esperando_confirmacion_modelo"
    GENERANDO_TRAYECTORIAS = "generando_trayectorias"
    SIMULANDO = "simulando"
    ESPERANDO_APROBACION_FINAL = "esperando_aprobacion_final"
    APROBADO = "aprobado"
    RECHAZADO = "rechazado"
    ERROR = "error"


# The three mandatory human checkpoints from Capa 6. The agent must not
# advance past any of these without an explicit confirmation event.
ETAPAS_QUE_REQUIEREN_APROBACION_HUMANA = frozenset(
    {
        Etapa.ESPERANDO_CONFIRMACION_EXTRACCION,
        Etapa.ESPERANDO_CONFIRMACION_MODELO,
        Etapa.ESPERANDO_APROBACION_FINAL,
    }
)


class ArchivoGenerado(BaseModel):
    nombre: str
    tipo: str = Field(description="step | stl | gcode | pdf_reporte")
    ruta: str
    generado_en: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    es_simulacion: bool = Field(
        default=False,
        description="True cuando el archivo NO proviene de SolidWorks/Mastercam reales",
    )


class EventoActividad(BaseModel):
    ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    etapa: Etapa
    titulo: str
    detalle: Optional[str] = None


class ToolpathPlan(BaseModel):
    """Output of Capa 4/5 planning (generar_trayectoria_mastercam), before
    any G-code exists. Real strategy/tooling selection, not simulated.
    """

    estrategia: str
    herramientas: list[dict] = Field(default_factory=list)
    tiempo_estimado_min: Optional[float] = None
    operaciones: list[dict] = Field(default_factory=list)
    advertencias: list[str] = Field(default_factory=list)


class Proyecto(BaseModel):
    id: str = Field(default_factory=lambda: f"AXC-{uuid.uuid4().hex[:8].upper()}")
    nombre: str
    etapa: Etapa = Etapa.PLANO_SUBIDO
    creado_en: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    actualizado_en: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    archivo_plano: Optional[str] = None
    pieza_extraida: Optional[Pieza] = None
    pieza_confirmada: bool = False

    modelo_confirmado: bool = False
    advertencias_modelo: list[str] = Field(default_factory=list)
    features_omitidos_modelo: list[str] = Field(default_factory=list)
    postprocesador: Optional[str] = None
    toolpath_plan: Optional[ToolpathPlan] = None
    simulacion: Optional[dict] = None
    codigo_g_resumen: Optional[dict] = None

    aprobacion_final: bool = False
    aprobado_por: Optional[str] = None
    aprobado_en: Optional[datetime] = None

    archivos: list[ArchivoGenerado] = Field(default_factory=list)
    actividad: list[EventoActividad] = Field(default_factory=list)
    mensajes: list[dict] = Field(
        default_factory=list, description="Historial crudo en formato Anthropic messages API, para continuar la conversacion"
    )

    def registrar_evento(self, titulo: str, detalle: Optional[str] = None) -> None:
        self.actividad.append(EventoActividad(etapa=self.etapa, titulo=titulo, detalle=detalle))
        self.actualizado_en = datetime.now(timezone.utc)
