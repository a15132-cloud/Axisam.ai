from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes_files, routes_kb, routes_projects
from app.config import settings

app = FastAPI(
    title="Axiscam Orchestrator",
    description="Capa 2-6 del agente Axiscam: extraccion de planos, base de conocimiento, "
    "puente de geometria, planeacion CAM y aprobacion humana.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_projects.router)
app.include_router(routes_files.router)
app.include_router(routes_kb.router)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "anthropic_configurado": bool(settings.anthropic_api_key),
        "capa4_solidworks": "geometria real via cadquery/OpenCascade - pendiente de sustituir por COM API en servidor Windows",
        "capa4_mastercam": "simulacion basada en reglas - pendiente de integracion con Mastercam SDK",
    }
