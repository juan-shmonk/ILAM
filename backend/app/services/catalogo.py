"""Carga de la configuración JSON (tipos de documento y requisitos)."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from app.config import CONFIG_DOCS_DIR

# Orden en el que se muestran y se usan como referencia cuando falta el documento base.
ORDEN_TIPOS = ["solicitud", "carta_aceptacion", "plan_trabajo"]


@lru_cache
def requisitos() -> dict[str, Any]:
    with open(CONFIG_DOCS_DIR / "requisitos.json", encoding="utf-8") as f:
        return json.load(f)


@lru_cache
def tipos_documento() -> dict[str, dict[str, Any]]:
    """Devuelve {codigo: configuracion} para todos los tipos definidos."""
    tipos: dict[str, dict[str, Any]] = {}
    for ruta in sorted(CONFIG_DOCS_DIR.glob("*.json")):
        if ruta.name == "requisitos.json":
            continue
        with open(ruta, encoding="utf-8") as f:
            cfg = json.load(f)
        tipos[cfg["codigo"]] = cfg
    return {c: tipos[c] for c in ORDEN_TIPOS if c in tipos} | {c: v for c, v in tipos.items() if c not in ORDEN_TIPOS}


def tipo(codigo: str) -> dict[str, Any] | None:
    return tipos_documento().get(codigo)
