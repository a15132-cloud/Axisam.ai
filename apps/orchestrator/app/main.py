from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes_files, routes_kb, routes_projects
from app.config import settings
from app.integrations import windows_bridge

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
    bridge = windows_bridge.estado_bridge()
    return {
        "status": "ok",
        "anthropic_configurado": bool(settings.anthropic_api_key),
        "capa4_solidworks": "geometria simulada via cadquery/OpenCascade - se usa SolidWorks real automaticamente "
        "cuando apps/windows-bridge esta corriendo en la maquina del usuario (ver bridge_windows)",
        "capa4_mastercam": "trayectorias simuladas basadas en reglas - se usara Mastercam real automaticamente "
        "cuando el conector correspondiente este implementado en apps/windows-bridge (ver bridge_windows)",
        "bridge_windows": bridge,
    }
