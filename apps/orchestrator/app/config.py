"""Process-wide settings, read once from the environment. No framework
magic - the orchestrator is small enough that plain env vars are enough
and keep the "what does this need to run" list obvious.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str
    claude_model_vision: str
    claude_model_agent: str
    storage_dir: str
    storage_dir_debe_ser_persistente: bool
    default_postprocessor: str
    cors_allow_origins: list[str]


def _normalizar_origenes_cors(valor: str) -> list[str]:
    """A browser's Origin header is always exactly scheme://host[:port] -
    never a trailing slash, never leading/trailing whitespace. FastAPI's
    CORSMiddleware does an EXACT string match against allow_origins, so a
    value like "https://x.vercel.app/" or " https://x.vercel.app" (both
    natural ways to type this by hand in Render's dashboard - a stray
    space after a comma, a trailing slash copied from the browser bar)
    would silently never match anything, and the browser reports that to
    the app as an opaque "Network Error" with zero indication it was CORS
    - looks exactly like "no internet" even though the server is healthy
    and reachable. Stripping both here removes an entire class of
    copy-paste misconfiguration that is otherwise invisible to whoever set
    the env var.
    """
    return [o.strip().rstrip("/") for o in valor.split(",") if o.strip()]


def _load() -> Settings:
    return Settings(
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        claude_model_vision=os.environ.get("AXISCAM_VISION_MODEL", "claude-sonnet-5"),
        claude_model_agent=os.environ.get("AXISCAM_AGENT_MODEL", "claude-sonnet-5"),
        storage_dir=os.environ.get("AXISCAM_STORAGE_DIR", "./data"),
        # Explicit opt-in, set only by render.yaml alongside AXISCAM_STORAGE_DIR=/data
        # - distinguishes "this deployment expects a real persistent disk,
        # treat 'not mounted right now' as a transient reconnect" (production)
        # from "this is local dev/tests, storage_dir is just a plain folder
        # by design, a 404 there always means the project genuinely doesn't
        # exist" (AXISCAM_STORAGE_PERSISTENTE unset everywhere else,
        # including in tests that point storage_dir at a tmp_path). Without
        # this flag, diagnostico_almacenamiento()'s st_dev check alone
        # can't tell those two cases apart - both look like "not a mount
        # point" - see _obtener_o_404 in routes_projects.py.
        storage_dir_debe_ser_persistente=os.environ.get("AXISCAM_STORAGE_PERSISTENTE", "false").lower() == "true",
        default_postprocessor=os.environ.get("AXISCAM_DEFAULT_POSTPROCESSOR", "haas_vf_generico"),
        cors_allow_origins=_normalizar_origenes_cors(os.environ.get("AXISCAM_CORS_ORIGINS", "http://localhost:5173")),
    )


settings = _load()
