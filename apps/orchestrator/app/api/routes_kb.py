"""Read-only endpoints exposing the Capa 5 knowledge base, so the frontend
can show material/postprocessor pickers instead of free-text fields."""

from __future__ import annotations

from fastapi import APIRouter

from app.knowledge_base import rules

router = APIRouter(prefix="/api/knowledge-base", tags=["knowledge-base"])


@router.get("/materiales")
def listar_materiales() -> list[dict]:
    return rules.listar_materiales()


@router.get("/postprocesadores")
def listar_postprocesadores() -> list[dict]:
    return rules.listar_postprocesadores()
