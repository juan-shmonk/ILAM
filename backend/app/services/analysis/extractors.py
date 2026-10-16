"""Extracción de campos a partir del texto, guiada por la configuración JSON.

Cada campo de ``config_docs/<tipo>.json`` declara sus etiquetas ("Matrícula",
"Nombre del alumno"...). El extractor busca líneas con la forma
``Etiqueta: valor`` (o la etiqueta sola y el valor en la línea siguiente).
Si el formato oficial real es distinto, se ajusta el JSON, no el código.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from app.services.analysis import textutil as tu

_RE_ITEM = re.compile(r"^(?:[-•*·▪●]|\d+[.)])\s*(.+)$")
_RE_OTRA_ETIQUETA = re.compile(r"^\s*[^:\n]{2,45}:\s")


@dataclass
class Campo:
    """Un dato extraído, con su valor original y normalizado."""

    crudo: str | list[str] | None = None  # texto tal como se leyó
    valor: Any = None  # valor tipado (str, fecha ISO, int, lista)
    normalizado: Any = None  # clave para comparar entre documentos
    valido: bool = False  # el valor pudo interpretarse según su tipo
    confianza: float = 0.0  # 0-1
    fuente: str = "regex"
    pagina: int | None = None  # página 1-indexada donde se encontró
    error: str | None = None
    ilegible: bool = False  # el dato parece existir (p. ej. imagen pegada) pero no se pudo leer

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def presente(self) -> bool:
        return self.crudo not in (None, "", [])


def _compilar(etiquetas: list[str]) -> re.Pattern[str]:
    ordenadas = sorted((tu.quitar_acentos(e) for e in etiquetas), key=len, reverse=True)
    alternativas = "|".join(re.escape(e) for e in ordenadas)
    return re.compile(rf"^\s*(?:{alternativas})\s*[:：]\s*(?P<v>.*?)\s*$", re.IGNORECASE)


def _lineas(paginas: list[str]) -> list[tuple[int, str]]:
    salida: list[tuple[int, str]] = []
    for n, texto in enumerate(paginas, start=1):
        for linea in texto.splitlines():
            salida.append((n, linea))
    return salida


def _buscar_etiqueta(
    lineas: list[tuple[int, str]], patron: re.Pattern[str], valor_en_siguiente: bool = True
) -> tuple[int, str, int] | None:
    """Devuelve (indice_linea, valor, pagina) de la primera línea que empieza con la etiqueta."""
    for i, (pagina, linea) in enumerate(lineas):
        sin_acentos = tu.quitar_acentos(linea)
        m = patron.match(sin_acentos)
        if not m:
            continue
        # Si las longitudes coinciden podemos tomar el valor del texto original (con acentos).
        if len(sin_acentos) == len(linea):
            valor = linea[m.start("v"): m.end("v")].strip()
        else:
            valor = m.group("v").strip()
        if not valor and valor_en_siguiente:  # el valor puede venir en la siguiente línea no vacía
            j = i + 1
            while j < len(lineas) and not lineas[j][1].strip():
                j += 1
            if j < len(lineas) and not _RE_OTRA_ETIQUETA.match(lineas[j][1]):
                valor = lineas[j][1].strip()
        return i, valor, pagina
    return None


def _extraer_lista(lineas: list[tuple[int, str]], indice: int, valor_inline: str) -> list[str]:
    items: list[str] = []
    if valor_inline:
        items.append(valor_inline)
    for _, linea in lineas[indice + 1:]:
        s = linea.strip()
        if not s:
            if items:
                break
            continue
        m = _RE_ITEM.match(s)
        if m:
            items.append(m.group(1).strip())
        elif items and s[0].islower():  # línea de continuación de un ítem largo
            items[-1] += " " + s
        else:
            break
    return items


def _construir(tipo: str, crudo: str, confianza: float, pagina: int | None) -> Campo:
    campo = Campo(crudo=crudo, confianza=confianza, pagina=pagina)
    if tipo == "fecha":
        d = tu.parse_fecha(crudo)
        campo.valido = d is not None
        campo.valor = d.isoformat() if d else None
        campo.normalizado = campo.valor
        if not d:
            campo.error = "formato de fecha no reconocido"
    elif tipo == "entero":
        n = tu.parse_entero(crudo)
        campo.valido = n is not None
        campo.valor = n
        campo.normalizado = n
        if n is None:
            campo.error = "no se encontró un número"
    elif tipo == "matricula":
        m = tu.normalizar_matricula(crudo)
        campo.valor = m
        campo.normalizado = m
        campo.valido = bool(m)
    elif tipo == "nombre":
        campo.valor = tu.limpiar_espacios(crudo)
        campo.normalizado = tu.normalizar_nombre(crudo)
        campo.valido = bool(campo.normalizado)
    else:  # texto
        campo.valor = tu.limpiar_espacios(crudo)
        campo.normalizado = tu.normalizar_texto(crudo)
        campo.valido = bool(campo.normalizado)
    return campo


def extraer_campos(paginas: list[str], cfg_campos: dict[str, dict[str, Any]], confianza: float) -> dict[str, Campo]:
    """Extrae todos los campos definidos en la configuración del tipo de documento.

    ``confianza`` es la confianza global de lectura (1.0 para texto digital,
    la confianza media del OCR en otro caso).
    """
    lineas = _lineas(paginas)
    resultado: dict[str, Campo] = {}
    for nombre, spec in cfg_campos.items():
        patron = _compilar(spec["etiquetas"])
        hallado = _buscar_etiqueta(lineas, patron, valor_en_siguiente=spec["tipo"] != "lista")
        if hallado is None:
            resultado[nombre] = Campo()  # ausente
            continue
        indice, valor, pagina = hallado
        if spec["tipo"] == "lista":
            items = _extraer_lista(lineas, indice, valor)
            resultado[nombre] = Campo(
                crudo=items or None,
                valor=items,
                normalizado=[tu.normalizar_texto(i) for i in items],
                valido=bool(items),
                confianza=confianza,
                pagina=pagina,
            )
        elif not valor:
            resultado[nombre] = Campo(pagina=pagina)  # etiqueta presente, valor vacío
        else:
            resultado[nombre] = _construir(spec["tipo"], valor, confianza, pagina)
    return resultado
