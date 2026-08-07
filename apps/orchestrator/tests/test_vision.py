"""Tests the extraction pipeline (schema plumbing, format handling, error
paths) against a fake Anthropic client - no network / API key needed.
Does not (and cannot, without a real key) verify Claude's actual reading
of a drawing; that needs a live smoke test once ANTHROPIC_API_KEY is set.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from app.vision.extractor import (
    ExtraccionError,
    FormatoNoSoportado,
    _build_content_blocks,
    extraer_pieza_desde_plano,
)

EJEMPLO_PIEZA_VALIDA = {
    "pieza": "placa_soporte",
    "tipo_maquinado": "fresado",
    "material": {"nombre": "Aluminio 6061"},
    "dimensiones": {"forma_base": "rectangular", "largo_mm": 100, "ancho_mm": 60, "espesor_mm": 10},
    "features": [{"tipo": "barreno", "diametro_mm": 8, "posicion": {"x": 50, "y": 30}}],
    "extraccion": {"confianza_global": 0.92, "campos_baja_confianza": []},
}


@dataclass
class _FakeToolUseBlock:
    input: dict
    name: str = "registrar_pieza_extraida"
    type: str = "tool_use"


class _FakeMessages:
    def __init__(self, tool_input: dict | None, stop_reason: str = "tool_use"):
        self._tool_input = tool_input
        self._stop_reason = stop_reason
        self.last_call_kwargs: dict | None = None

    def create(self, **kwargs):
        self.last_call_kwargs = kwargs
        content = [_FakeToolUseBlock(input=self._tool_input)] if self._tool_input is not None else []
        return SimpleNamespace(content=content, stop_reason=self._stop_reason)


class _FakeClient:
    def __init__(self, tool_input: dict | None, stop_reason: str = "tool_use"):
        self.messages = _FakeMessages(tool_input, stop_reason)


def test_extraccion_exitosa_con_imagen():
    client = _FakeClient(EJEMPLO_PIEZA_VALIDA)
    resultado = extraer_pieza_desde_plano(b"fake-png-bytes", "image/png", "plano.png", client=client)

    assert resultado.pieza.pieza == "placa_soporte"
    assert resultado.pieza.material.nombre == "Aluminio 6061"
    # tool_choice must force the extraction tool, otherwise Claude could reply with plain text
    assert client.messages.last_call_kwargs["tool_choice"] == {"type": "tool", "name": "registrar_pieza_extraida"}


def test_extraccion_pdf_usa_bloque_document():
    bloques = _build_content_blocks(b"%PDF-1.4 fake", "application/pdf", "plano.pdf")
    assert bloques[0]["type"] == "document"
    assert bloques[0]["source"]["media_type"] == "application/pdf"


def test_extraccion_dxf_usa_resumen_textual():
    import ezdxf
    import io

    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    msp.add_circle((50, 30), radius=4)
    buf = io.StringIO()
    doc.write(buf)
    contenido = buf.getvalue().encode("utf-8")

    bloques = _build_content_blocks(contenido, "", "plano.dxf")
    assert bloques[0]["type"] == "text"
    assert "50.000" in bloques[0]["text"]


def test_extraccion_dwg_no_soportado():
    with pytest.raises(FormatoNoSoportado, match="dwg"):
        _build_content_blocks(b"binary junk", "application/acad", "plano.dwg")


def test_extraccion_formato_desconocido():
    with pytest.raises(FormatoNoSoportado):
        _build_content_blocks(b"???", "application/x-weird", "plano.xyz")


def test_extraccion_sin_tool_use_lanza_error():
    client = _FakeClient(tool_input=None, stop_reason="end_turn")
    with pytest.raises(ExtraccionError, match="no devolvio una extraccion"):
        extraer_pieza_desde_plano(b"bytes", "image/png", "plano.png", client=client)


def test_extraccion_con_json_invalido_lanza_error_legible():
    invalido = {"pieza": "x"}  # missing required material/dimensiones
    client = _FakeClient(invalido)
    with pytest.raises(ExtraccionError, match="no cumple el formato esperado"):
        extraer_pieza_desde_plano(b"bytes", "image/png", "plano.png", client=client)


def test_instrucciones_usuario_se_incluyen_en_el_mensaje():
    client = _FakeClient(EJEMPLO_PIEZA_VALIDA)
    extraer_pieza_desde_plano(
        b"bytes", "image/png", "plano.png", instrucciones_usuario="material aluminio, tolerancia estandar", client=client
    )
    contenido = client.messages.last_call_kwargs["messages"][0]["content"]
    assert any("tolerancia estandar" in b.get("text", "") for b in contenido if b["type"] == "text")
