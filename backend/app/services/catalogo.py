"""Carga de la configuración JSON (tipos de documento, formatos y requisitos).

Un *tipo* de documento (solicitud, plan de trabajo...) puede tener varios
*formatos*: la institución cambia sus plantillas con el tiempo y además
existen los formatos sintéticos que usa el proyecto para pruebas. Cada archivo
``config_docs/*.json`` describe UN formato:

    "codigo":  tipo de documento al que pertenece ("plan_trabajo")
    "formato": identificador del formato ("ITC-VI-PO-002-07-rev0")
    "principal": true  -> formato que se muestra en la interfaz para ese tipo
    "identificadores": textos que deben aparecer TODOS para reconocer el formato

El pipeline elige el formato cuyo conjunto de identificadores coincide con el
texto leído (ver ``elegir_formato``).
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from app.config import CONFIG_DOCS_DIR
from app.services.analysis import textutil as tu

# Orden en el que se muestran y se usan como referencia cuando falta el documento base.
ORDEN_TIPOS = ["solicitud", "plan_trabajo"]


@lru_cache
def requisitos() -> dict[str, Any]:
    with open(CONFIG_DOCS_DIR / "requisitos.json", encoding="utf-8") as f:
        return json.load(f)


@lru_cache
def _todos_los_formatos() -> dict[str, list[dict[str, Any]]]:
    """{codigo: [formato, ...]} con el formato principal primero."""
    por_tipo: dict[str, list[dict[str, Any]]] = {}
    for ruta in sorted(CONFIG_DOCS_DIR.glob("*.json")):
        if ruta.name == "requisitos.json":
            continue
        with open(ruta, encoding="utf-8") as f:
            cfg = json.load(f)
        cfg.setdefault("formato", ruta.stem)
        por_tipo.setdefault(cfg["codigo"], []).append(cfg)
    for lista in por_tipo.values():
        lista.sort(key=lambda c: not c.get("principal", False))
    return por_tipo


@lru_cache
def tipos_documento() -> dict[str, dict[str, Any]]:
    """Devuelve {codigo: formato_principal} para todos los tipos definidos."""
    tipos = {c: fs[0] for c, fs in _todos_los_formatos().items()}
    return {c: tipos[c] for c in ORDEN_TIPOS if c in tipos} | {c: v for c, v in tipos.items() if c not in ORDEN_TIPOS}


def tipo(codigo: str) -> dict[str, Any] | None:
    return tipos_documento().get(codigo)


def formatos(codigo: str) -> list[dict[str, Any]]:
    return list(_todos_los_formatos().get(codigo, []))


def formato(codigo: str, version: str | None) -> dict[str, Any] | None:
    """Configuración de un formato concreto; si no existe, la del formato principal."""
    for cfg in formatos(codigo):
        if cfg["formato"] == version:
            return cfg
    return tipo(codigo)


def elegir_formato(codigo: str, texto: str) -> dict[str, Any] | None:
    """Elige el formato de ``codigo`` que mejor corresponde al texto leído.

    Gana el formato con más identificadores, siempre que aparezcan todos. Si
    ninguno coincide se usa el principal (y la regla R005 dirá si el documento
    no es del tipo esperado).
    """
    normal = tu.normalizar_texto(texto)
    mejor: tuple[int, dict[str, Any]] | None = None
    for cfg in formatos(codigo):
        ids = [tu.normalizar_texto(i) for i in cfg.get("identificadores", [])]
        if ids and all(i in normal for i in ids) and (mejor is None or len(ids) > mejor[0]):
            mejor = (len(ids), cfg)
    return mejor[1] if mejor else tipo(codigo)
