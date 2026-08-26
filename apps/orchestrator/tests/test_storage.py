import dataclasses
from pathlib import Path
from types import SimpleNamespace

from app.storage import files as storage


def test_diagnostico_detecta_carpeta_normal_como_no_persistente(tmp_path, monkeypatch):
    """tmp_path es siempre una subcarpeta normal del mismo filesystem - el
    caso real que causa "proyectos que se pierden" en Render plan Free. Solo
    importa (y solo entonces se arma la advertencia) en un deploy que
    explicitamente espera un disco persistente real - ver
    storage_dir_debe_ser_persistente y el siguiente test para el caso
    contrario (desktop/dev local).
    """
    destino = tmp_path / "data"
    destino.mkdir()
    monkeypatch.setattr(storage, "_base_dir", lambda: destino)
    monkeypatch.setattr(storage, "settings", dataclasses.replace(storage.settings, storage_dir_debe_ser_persistente=True))

    resultado = storage.diagnostico_almacenamiento()

    assert resultado["es_punto_de_montaje"] is False
    assert "se BORRAN en cada redeploy" in resultado["advertencia"]
    assert str(destino) in resultado["ruta"]


def test_diagnostico_no_advierte_cuando_no_se_espera_disco_persistente(tmp_path, monkeypatch):
    """La app de escritorio (apps/desktop) y el dev local nunca configuran
    AXISCAM_STORAGE_PERSISTENTE - ahi `storage_dir` es una carpeta normal y
    permanente en el disco real del usuario, nunca va a ser un "punto de
    montaje separado", y eso es completamente normal, no una falla. Bug real
    que esto cubre: la app de escritorio mostraba el mismo banner rojo de
    "confirma tu plan en Render" a un usuario que nunca toco Render.
    """
    destino = tmp_path / "data"
    destino.mkdir()
    monkeypatch.setattr(storage, "_base_dir", lambda: destino)
    monkeypatch.setattr(storage, "settings", dataclasses.replace(storage.settings, storage_dir_debe_ser_persistente=False))

    resultado = storage.diagnostico_almacenamiento()

    assert resultado["es_punto_de_montaje"] is False
    assert resultado["advertencia"] is None


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
