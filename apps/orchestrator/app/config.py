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
    default_postprocessor: str
    cors_allow_origins: list[str]


def _load() -> Settings:
    return Settings(
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        claude_model_vision=os.environ.get("AXISCAM_VISION_MODEL", "claude-sonnet-5"),
        claude_model_agent=os.environ.get("AXISCAM_AGENT_MODEL", "claude-sonnet-5"),
        storage_dir=os.environ.get("AXISCAM_STORAGE_DIR", "./data"),
        default_postprocessor=os.environ.get("AXISCAM_DEFAULT_POSTPROCESSOR", "haas_vf_generico"),
        cors_allow_origins=os.environ.get("AXISCAM_CORS_ORIGINS", "http://localhost:5173").split(","),
    )


settings = _load()
