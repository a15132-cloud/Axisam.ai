from app.config import _normalizar_origenes_cors


def test_normaliza_espacios_despues_de_la_coma():
    """Forma natural de escribirlo a mano en el dashboard de Render: un
    espacio despues de cada coma. Sin normalizar, el segundo origen nunca
    hace match contra el header Origin real del navegador (que nunca trae
    espacios) y CORS lo bloquea en silencio.
    """
    assert _normalizar_origenes_cors("https://a.vercel.app, https://b.vercel.app") == [
        "https://a.vercel.app",
        "https://b.vercel.app",
    ]


def test_normaliza_slash_final():
    """Copiar la URL desde la barra del navegador a veces trae un / final -
    el header Origin real nunca lo tiene (es solo scheme://host[:puerto]).
    """
    assert _normalizar_origenes_cors("https://axisam-ai.vercel.app/") == ["https://axisam-ai.vercel.app"]


def test_ignora_entradas_vacias_por_coma_final():
    assert _normalizar_origenes_cors("https://a.vercel.app,") == ["https://a.vercel.app"]


def test_un_solo_origen_sin_coma_sigue_funcionando():
    assert _normalizar_origenes_cors("http://localhost:5173") == ["http://localhost:5173"]
