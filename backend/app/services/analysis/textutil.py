"""Utilidades de normalización de texto, nombres, fechas y números.

Todo aquí es determinístico y sin dependencias pesadas: las mismas entradas
siempre producen las mismas salidas, lo que hace explicables las reglas.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
MESES_NOMBRE = [
    "", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
    "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]

# Títulos que suelen anteponerse a un nombre y no deben afectar la comparación.
_TITULOS = {"c", "lic", "ing", "dr", "dra", "mtro", "mtra", "sr", "sra", "arq", "m", "c."}

_RE_ISO = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
_RE_NUM = re.compile(r"\b(\d{1,2})\s*[/\-.]\s*(\d{1,2})\s*[/\-.]\s*(\d{2,4})\b")
_RE_TXT = re.compile(r"\b(\d{1,2})[.,]?\s+de\s+([A-Za-zÁÉÍÓÚáéíóúñÑ]+)\s+(?:de|del)?\s*(\d{4})\b", re.IGNORECASE)


def quitar_acentos(texto: str) -> str:
    """Quita marcas diacríticas (á -> a, ñ -> n)."""
    descompuesto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in descompuesto if not unicodedata.combining(c))


def normalizar_texto(texto: str) -> str:
    """Minúsculas, sin acentos ni signos, espacios colapsados."""
    texto = quitar_acentos(texto).casefold()
    texto = re.sub(r"[^\w\s]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def limpiar_espacios(texto: str) -> str:
    return re.sub(r"\s+", " ", texto).strip()


def normalizar_nombre(texto: str) -> str:
    """Normaliza un nombre de persona para compararlo (sin títulos ni acentos)."""
    tokens = [t for t in normalizar_texto(texto).split() if t not in _TITULOS]
    return " ".join(tokens)


def normalizar_matricula(texto: str) -> str:
    return re.sub(r"[\s\-]", "", texto).upper()


def parse_fecha(texto: str) -> date | None:
    """Interpreta fechas comunes en español. Devuelve None si no puede.

    Acepta: 15/02/2027, 15-02-2027, 15.02.27, 2027-02-15 y "15 de febrero de 2027".
    Siempre se interpreta día/mes/año.
    """
    if not texto:
        return None
    m = _RE_ISO.search(texto)
    if m:
        anio, mes, dia = (int(g) for g in m.groups())
        return _crear_fecha(anio, mes, dia)
    m = _RE_NUM.search(texto)
    if m:
        dia, mes, anio = (int(g) for g in m.groups())
        if anio < 100:
            anio += 2000
        return _crear_fecha(anio, mes, dia)
    m = _RE_TXT.search(texto)
    if m:
        dia = int(m.group(1))
        mes = MESES.get(quitar_acentos(m.group(2)).casefold())
        anio = int(m.group(3))
        if mes:
            return _crear_fecha(anio, mes, dia)
    return None


def _crear_fecha(anio: int, mes: int, dia: int) -> date | None:
    try:
        return date(anio, mes, dia)
    except ValueError:
        return None


def formatear_fecha(iso: str | None) -> str:
    """'2027-02-15' -> '15/02/2027' (formato para mostrar al alumno)."""
    if not iso:
        return "(vacío)"
    try:
        d = date.fromisoformat(iso)
    except ValueError:
        return str(iso)
    return f"{d.day:02d}/{d.month:02d}/{d.year}"


def parse_entero(texto: str) -> int | None:
    """Primer entero encontrado: '480 horas' -> 480, '1,200' -> 1200."""
    if not texto:
        return None
    m = re.search(r"\d[\d,\.]*", texto)
    if not m:
        return None
    limpio = re.sub(r"[,\.]", "", m.group(0))
    try:
        return int(limpio)
    except ValueError:
        return None


def meses_entre(inicio: date, fin: date) -> float:
    """Duración en meses calendario: del 15/02 al 15/08 son exactamente 6.0."""
    meses = (fin.year - inicio.year) * 12 + (fin.month - inicio.month)
    return meses + (fin.day - inicio.day) / 30.44
