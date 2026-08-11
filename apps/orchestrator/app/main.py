from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes_convert, routes_files, routes_kb, routes_projects
from app.config import settings
from app.integrations import windows_bridge
from app.storage import files as storage

app = FastAPI(
    title="Axiscam Orchestrator",
    description="Capa 2-6 del agente Axiscam: extraccion de planos, base de conocimiento, "
    "puente de geometria, planeacion CAM y aprobacion humana.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    # Deliberately permissive, unconditionally - not driven by
    # AXISCAM_CORS_ORIGINS anymore. That env var (see render.yaml/config.py)
    # requires an exact match to whatever domain the frontend happens to be
    # served from, and Vercel hands out a NEW url for every preview
    # deployment on top of the stable production one - a mismatch there
    # (wrong value, stale value, testing from a preview link instead of
    # production) silently blocks every request from the browser with an
    # error that looks identical to "the internet is down" (see
    # apps/web/src/lib/api.ts's diagnosticarNetworkError). This API has no
    # cookie/session-based auth for CORS to protect in the first place - the
    # frontend never sets withCredentials, and the shared ANTHROPIC_API_KEY
    # is a server-side secret never exposed to the browser regardless of
    # origin - so restricting the origin list here bought safety this app
    # doesn't need at the cost of a whole recurring class of deployment
    # failures. Anyone who wants to call this API directly already can, from
    # curl or a script, with zero regard for CORS; the browser-only
    # restriction was never a real barrier to that.
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_projects.router)
app.include_router(routes_files.router)
app.include_router(routes_kb.router)
app.include_router(routes_convert.router)


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
        "almacenamiento": storage.diagnostico_almacenamiento(),
    }
