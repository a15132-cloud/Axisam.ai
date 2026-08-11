from pathlib import Path
from types import SimpleNamespace

from app.storage import files as storage


def test_diagnostico_detecta_carpeta_normal_como_no_persistente(tmp_path, monkeypatch):
    """tmp_path es siempre una subcarpeta normal del mismo filesystem - el
    caso real que causa "proyectos que se pierden" en Render plan Free.
    """
    destino = tmp_path / "data"
    destino.mkdir()
    monkeypatch.setattr(storage, "_base_dir", lambda: destino)

    resultado = storage.diagnostico_almacenamiento()

    assert resultado["es_punto_de_montaje"] is False
    assert "se BORRAN en cada redeploy" in resultado["advertencia"]
    assert str(destino) in resultado["ruta"]


def test_diagnostico_detecta_punto_de_montaje_real(tmp_path, monkeypatch):
    """Simula un disco persistente real: st_dev distinto al de la carpeta
    padre (la misma senal que usa `mountpoint` en Linux).
    """
    destino = tmp_path / "data"
    destino.mkdir()
    monkeypatch.setattr(storage, "_base_dir", lambda: destino)

    # diagnostico_almacenamiento() only reads .st_dev off the result, so a
    # minimal fake is enough - no need to build a real os.stat_result.
    def stat_falso(self, *args, **kwargs):
        return SimpleNamespace(st_dev=1 if self == destino else 2)

    monkeypatch.setattr(Path, "stat", stat_falso)

    resultado = storage.diagnostico_almacenamiento()

    assert resultado["es_punto_de_montaje"] is True
    assert resultado["advertencia"] is None
