"""Configuración de la aplicación.

Los valores se pueden sobrescribir con variables de entorno que empiecen con
``PREVAL_`` o con un archivo ``.env`` (ver ``.env.example``). Nunca se guardan
claves dentro del código.
"""

from __future__ import annotations

import secrets
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BACKEND_DIR / "data"
CONFIG_DOCS_DIR = Path(__file__).resolve().parent / "config_docs"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="PREVAL_", extra="ignore")

    # Si no se define, se genera una clave aleatoria y se guarda en data/secret_key.txt
    secret_key: str | None = None
    database_url: str = f"sqlite:///{(DATA_DIR / 'prevalidador.db').as_posix()}"
    storage_dir: Path = DATA_DIR / "storage"

    cookie_secure: bool = False  # poner True cuando se sirva por HTTPS
    session_hours: int = 8
    max_upload_mb: int = 15
    max_paginas: int = 20

    # OCR (opcional). En Windows, si Tesseract no está en el PATH, indicar la ruta
    # completa, por ejemplo: C:\Program Files\Tesseract-OCR\tesseract.exe
    ocr_lang: str = "spa"
    tesseract_cmd: str | None = None

    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_secret_key() -> str:
    """Clave para firmar sesiones: la del entorno o una generada y persistida."""
    settings = get_settings()
    if settings.secret_key:
        return settings.secret_key
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    archivo = DATA_DIR / "secret_key.txt"
    if archivo.exists():
        return archivo.read_text(encoding="utf-8").strip()
    clave = secrets.token_urlsafe(48)
    archivo.write_text(clave, encoding="utf-8")
    return clave
