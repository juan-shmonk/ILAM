"""Configuración de pruebas: base de datos y almacenamiento temporales."""

import os
import tempfile
from pathlib import Path

# Debe ejecutarse ANTES de importar la aplicación.
_TMP = Path(tempfile.mkdtemp(prefix="prevalidador_test_"))
os.environ["PREVAL_DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["PREVAL_STORAGE_DIR"] = str(_TMP / "storage")
os.environ["PREVAL_SECRET_KEY"] = "clave-solo-para-pruebas-de-32-bytes-minimo-ok"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from scripts.generar_muestras import ESCENARIOS, generar_escenario  # noqa: E402


@pytest.fixture(scope="session")
def muestras(tmp_path_factory) -> Path:
    """Genera los 16 escenarios sintéticos una sola vez por sesión de pruebas."""
    base = tmp_path_factory.mktemp("muestras")
    for esc in ESCENARIOS:
        generar_escenario(esc, base / esc["id"])
    return base


@pytest.fixture()
def cliente():
    from app.main import app

    with TestClient(app) as c:
        yield c
