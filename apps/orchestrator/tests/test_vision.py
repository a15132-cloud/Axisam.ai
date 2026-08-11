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
    extraer_primera_pasada,
    verificar_segunda_pasada,
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
    """`respuestas` is a list of tool_input dicts (or None) consumed one per
    call, in order - the first is the initial extraction pass, the second
    (if present) is the verification pass's response. If there are fewer
    entries than calls made, the last entry repeats (covers tests that
    only care about a single, uniform response across both passes).
    """

    def __init__(self, respuestas: list[dict | None], stop_reason: str = "tool_use"):
        self._respuestas = respuestas
        self._stop_reason = stop_reason
        self.llamadas: list[dict] = []

    @property
    def last_call_kwargs(self) -> dict | None:
        return self.llamadas[-1] if self.llamadas else None

    def create(self, **kwargs):
        self.llamadas.append(kwargs)
        indice = min(len(self.llamadas) - 1, len(self._respuestas) - 1)
        tool_input = self._respuestas[indice]
        content = [_FakeToolUseBlock(input=tool_input)] if tool_input is not None else []
        return SimpleNamespace(content=content, stop_reason=self._stop_reason)


class _FakeClient:
    def __init__(self, tool_input: dict | list[dict | None] | None, stop_reason: str = "tool_use"):
        respuestas = tool_input if isinstance(tool_input, list) else [tool_input]
        self.messages = _FakeMessages(respuestas, stop_reason)


def test_extraccion_exitosa_con_imagen():
    client = _FakeClient(EJEMPLO_PIEZA_VALIDA)
    resultado = extraer_pieza_desde_plano(b"fake-png-bytes", "image/png", "plano.png", client=client)

    assert resultado.pieza.pieza == "placa_soporte"
    assert resultado.pieza.material.nombre == "Aluminio 6061"
    # tool_choice must force the extraction tool, otherwise Claude could reply with plain text
    assert client.messages.last_call_kwargs["tool_choice"] == {"type": "tool", "name": "registrar_pieza_extraida"}


def test_extraccion_imagen_sin_media_type_usa_extension_del_archivo():
    """Needed for the verification pass's HTTP request (see
    verificar_segunda_pasada), which re-reads the plano straight off disk -
    there's no browser-supplied Content-Type at that point, just the
    filename saved alongside the bytes.
    """
    bloques = _build_content_blocks(b"fake-png-bytes", "", "plano.png")
    assert bloques[0]["type"] == "image"
    assert bloques[0]["source"]["media_type"] == "image/png"


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
    contenido = client.messages.llamadas[0]["messages"][0]["content"]  # the initial pass, not the verification pass
    assert any("tolerancia estandar" in b.get("text", "") for b in contenido if b["type"] == "text")


def test_verificacion_es_una_segunda_llamada_independiente():
    """The self-review pass (added after a real client drawing exposed a
    missed feature that only surfaced on a slower second read) must
    actually happen - not just be plumbing that never fires.
    """
    client = _FakeClient(EJEMPLO_PIEZA_VALIDA)
    extraer_pieza_desde_plano(b"bytes", "image/png", "plano.png", client=client)

    assert len(client.messages.llamadas) == 2
    assert client.messages.llamadas[0]["system"] != client.messages.llamadas[1]["system"]
    # the verification pass must receive the first pass's JSON, not re-derive from nothing
    contenido_verificacion = client.messages.llamadas[1]["messages"][0]["content"]
    assert any("placa_soporte" in b.get("text", "") for b in contenido_verificacion if b["type"] == "text")


def test_verificacion_puede_corregir_la_primera_pasada():
    """If the second pass finds something real (exactly what happened with
    the DeAcero blade), its corrected JSON - not the first pass's - is
    what the caller gets back.
    """
    corregido = {**EJEMPLO_PIEZA_VALIDA, "pieza": "placa_soporte_corregida"}
    client = _FakeClient([EJEMPLO_PIEZA_VALIDA, corregido])
    resultado = extraer_pieza_desde_plano(b"bytes", "image/png", "plano.png", client=client)
    assert resultado.pieza.pieza == "placa_soporte_corregida"


def test_verificacion_fallida_no_pierde_la_primera_pasada():
    """The review pass is a quality upgrade, not a hard dependency - if it
    errors out (bad JSON, no tool call), the caller still gets the first
    pass's working result instead of losing the extraction entirely.
    """
    client = _FakeClient([EJEMPLO_PIEZA_VALIDA, None])  # second call returns no tool_use
    resultado = extraer_pieza_desde_plano(b"bytes", "image/png", "plano.png", client=client)
    assert resultado.pieza.pieza == "placa_soporte"


def test_las_dos_pasadas_por_separado_dan_el_mismo_resultado_que_juntas():
    """Regression test for the split introduced to keep each HTTP request
    comfortably under a hosting platform's own proxy timeout (see the
    docstrings on extraer_primera_pasada/verificar_segunda_pasada) - a real
    upload landed right at the edge of Render's own request timeout with
    both Claude calls inside one request, which the app has no way to
    configure around since it isn't this app's own timeout setting. Calling
    the two passes as separate functions (so routes_projects.py can expose
    them as separate endpoints) must produce the exact same end result as
    the combined convenience wrapper.
    """
    corregido = {**EJEMPLO_PIEZA_VALIDA, "pieza": "placa_soporte_corregida"}

    client_junto = _FakeClient([EJEMPLO_PIEZA_VALIDA, corregido])
    resultado_junto = extraer_pieza_desde_plano(b"bytes", "image/png", "plano.png", client=client_junto)

    client_separado = _FakeClient([EJEMPLO_PIEZA_VALIDA, corregido])
    primera = extraer_primera_pasada(b"bytes", "image/png", "plano.png", client=client_separado)
    assert primera.pieza.pieza == "placa_soporte"  # first pass alone, not yet verified
    segunda = verificar_segunda_pasada(b"bytes", "image/png", "plano.png", primera, client=client_separado)

    assert segunda.pieza.pieza == resultado_junto.pieza.pieza == "placa_soporte_corregida"
    assert len(client_separado.messages.llamadas) == 2


def test_segunda_pasada_por_separado_tambien_absorbe_fallas():
    client = _FakeClient([EJEMPLO_PIEZA_VALIDA, None])
    primera = extraer_primera_pasada(b"bytes", "image/png", "plano.png", client=client)
    segunda = verificar_segunda_pasada(b"bytes", "image/png", "plano.png", primera, client=client)
    assert segunda.pieza.pieza == "placa_soporte"
