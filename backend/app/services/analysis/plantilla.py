"""Extracción por PLANTILLA: cada campo se lee de una zona fija del formato oficial.

Por qué existe
--------------
Los formatos oficiales del Tec (ITC-VI-PO-002-xx) se diseñaron para llenarse a
mano: no tienen la forma ``Etiqueta: valor``, sino líneas de guiones bajos con
un número entre paréntesis, p. ej.::

    Carrera: (2) ____________________ No de Control (3) ___22530305___

Además, al llenarlos en Google Docs muchos valores terminan como IMÁGENES
pegadas encima de la línea: el PDF tiene texto digital, pero el dato no existe
como texto. Buscar etiquetas con expresiones regulares no funciona con eso.

Cómo funciona
-------------
1. Se obtienen las palabras de la página con su posición (texto digital del
   PDF, o las palabras del OCR si la página es un escaneo o una foto).
2. Para cada campo se localiza su ANCLA: el número impreso del formato
   ("(5)") o una etiqueta ("Fecha de Inicio"). Esas marcas no cambian aunque el
   alumno escriba más o menos texto.
3. A partir del ancla se calcula la ZONA del valor (a la derecha hasta la
   siguiente etiqueta, debajo hasta otra marca, o una caja relativa). Las
   distancias se expresan en "alturas del ancla" (``h``), así la misma
   plantilla sirve para un PDF (puntos) y para una foto (píxeles).
4. Se lee la zona: si en ella hay una imagen incrustada (o la página es un
   escaneo) se hace OCR solo de ese recorte; si no, se usa el texto digital.
5. Se limpia el valor (guiones bajos, marcas "(n)") y se interpreta según su
   tipo (fecha, matrícula, nombre...).

Todo es determinístico y la plantilla vive en ``config_docs/<tipo>.json``: si
la institución mueve un campo, se ajusta el JSON, no el código.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pymupdf as fitz
from PIL import Image

from app.services.analysis import ocr
from app.services.analysis import textutil as tu
from app.services.analysis.extractors import Campo, _construir
from app.services.analysis.signature import COBERTURA_MIN_X, ResultadoFirma, medir_tinta
from app.services.analysis.text_extraction import DPI_OCR, TextoDocumento

DPI_ZONA_OCR = 300
DPI_ZONA_FIRMA = 150
MARGEN_DER = 0.97  # fracción del ancho de página donde termina una zona "hasta el margen"
MARGEN_IZQ = 0.03

_RE_MARCA = re.compile(r"^\(\w{1,3}\)$")
_RE_MARCA_EN_TEXTO = re.compile(r"\(\s*\d{1,2}\s*\)")
_INVISIBLES = dict.fromkeys(map(ord, "​‌‍﻿"), None)

# Palabras con las que suele empezar el cargo bajo un nombre ("Jefe del centro de cómputo").
_CARGOS = {
    "jefe", "jefa", "director", "directora", "subdirector", "subdirectora", "coordinador", "coordinadora",
    "encargado", "encargada", "responsable", "titular", "gerente", "rector", "rectora", "presidente",
    "presidenta", "secretario", "secretaria", "supervisor", "supervisora", "administrador", "administradora",
    "auxiliar", "asesor", "asesora", "docente", "profesor", "profesora", "delegado", "delegada",
}


# ----------------------------------------------------------------------------
# Geometría
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class Caja:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def h(self) -> float:
        return max(self.y1 - self.y0, 1.0)

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    def contiene_centro(self, otra: "Caja") -> bool:
        return self.x0 <= otra.cx <= self.x1 and self.y0 <= otra.cy <= self.y1

    def intersecta(self, otra: "Caja") -> bool:
        return not (otra.x1 <= self.x0 or otra.x0 >= self.x1 or otra.y1 <= self.y0 or otra.y0 >= self.y1)

    def valida(self) -> bool:
        return self.x1 > self.x0 and self.y1 > self.y0

    def union(self, otra: "Caja") -> "Caja":
        return Caja(min(self.x0, otra.x0), min(self.y0, otra.y0), max(self.x1, otra.x1), max(self.y1, otra.y1))


@dataclass
class PalabraLayout:
    caja: Caja
    texto: str
    conf: float = 100.0  # 0-100; 100 para texto digital


@dataclass
class Layout:
    """Una página como palabras con posición, más una forma de recortar zonas como imagen."""

    numero: int  # 1-indexada
    palabras: list[PalabraLayout]
    ancho: float
    alto: float
    origen: str  # "digital" | "ocr"
    # Imágenes incrustadas (solo PDF digital): su caja y cómo obtener la imagen original.
    imagenes: list[tuple[Caja, Callable[[], Image.Image | None]]] = field(default_factory=list)
    _recortar: Callable[[Caja, int], Image.Image] | None = None

    def recorte(self, caja: Caja, dpi: int) -> Image.Image | None:
        caja = Caja(max(caja.x0, 0), max(caja.y0, 0), min(caja.x1, self.ancho), min(caja.y1, self.alto))
        if not caja.valida() or self._recortar is None:
            return None
        return self._recortar(caja, dpi)

    def imagenes_en(self, zona: Caja) -> list[tuple[Caja, Callable[[], Image.Image | None]]]:
        """Imágenes cuyo centro cae dentro de la zona (las que están "en el espacio" del campo)."""
        return [(c, f) for c, f in self.imagenes if zona.contiene_centro(c)]


_RE_SEPARADOR = re.compile(r"_+|(?=\(\d{1,2}\))|(?<=\(\d\))|(?<=\(\d\d\))")


def partir_palabra(p: PalabraLayout) -> list[PalabraLayout]:
    """Separa lo que el formato pegó en una sola "palabra".

    Al llenar el formato en un procesador de texto el valor queda unido a los
    guiones bajos y a la etiqueta siguiente: ``22530305______Carrera:`` o
    ``Dependencia:(5)``. Se parte en guiones bajos y alrededor de las marcas
    "(n)", repartiendo la caja en proporción a los caracteres.
    """
    texto = p.texto
    if "_" not in texto and not re.search(r".\(\d{1,2}\)|\(\d{1,2}\).", texto):
        return [p]
    ancho = (p.caja.x1 - p.caja.x0) / max(len(texto), 1)
    partes, inicio = [], 0
    for m in list(_RE_SEPARADOR.finditer(texto)) + [None]:
        fin = m.start() if m else len(texto)
        trozo = texto[inicio:fin]
        if trozo.strip():
            izq = inicio + len(trozo) - len(trozo.lstrip())
            der = izq + len(trozo.strip())
            partes.append(PalabraLayout(
                Caja(p.caja.x0 + ancho * izq, p.caja.y0, p.caja.x0 + ancho * der, p.caja.y1), trozo.strip(), p.conf))
        if m:
            inicio = m.end()
    return partes


def _cargador_imagen(doc: fitz.Document, xref: int) -> Callable[[], Image.Image | None]:
    """Devuelve una función que extrae la imagen incrustada ``xref`` en escala de grises sobre fondo blanco.

    Leer la imagen original (y no un recorte de la página renderizada) evita
    que el OCR se confunda con la línea de guiones bajos que pasa por debajo.
    """
    def cargar() -> Image.Image | None:
        if xref <= 0:
            return None
        try:
            pix = fitz.Pixmap(doc, xref)
            tipo, valor = doc.xref_get_key(xref, "SMask")
            if tipo == "xref":  # transparencia: en estos formatos el texto suele estar en la máscara
                pix = fitz.Pixmap(pix, fitz.Pixmap(doc, int(valor.split()[0])))
            if pix.colorspace and pix.colorspace.n not in (1, 3):
                pix = fitz.Pixmap(fitz.csRGB, pix)
            modo = {1: "L", 3: "RGB"}[pix.colorspace.n if pix.colorspace else 1]
            if pix.alpha:
                img = Image.frombytes(modo + "A" if modo == "RGB" else "LA", (pix.width, pix.height), pix.samples)
                fondo = Image.new("RGBA", img.size, (255, 255, 255, 255))
                img = Image.alpha_composite(fondo, img.convert("RGBA"))
            else:
                img = Image.frombytes(modo, (pix.width, pix.height), pix.samples)
            return img.convert("L")
        except Exception:  # imagen con formato raro: se usará un recorte de la página
            return None
    return cargar


def _layout_pdf_digital(pagina: fitz.Page, numero: int) -> Layout:
    palabras = []
    for w in pagina.get_text("words"):
        texto = w[4].translate(_INVISIBLES).strip()
        if texto:
            palabras.extend(partir_palabra(PalabraLayout(Caja(*w[:4]), texto)))
    imagenes = []
    # Se localiza cada imagen por su NOMBRE en el contenido de la página. get_image_info y
    # get_image_rects identifican imágenes por su contenido, y en estos formatos todas las
    # imágenes pegadas tienen el mismo fondo (el texto está en la máscara), así que las confunden.
    area_pagina = pagina.rect.width * pagina.rect.height
    for item in pagina.get_images(full=True):
        try:
            rects = [pagina.get_image_bbox(item)]
        except Exception:
            rects = []
        if not rects or not rects[0].is_valid or rects[0].is_empty or rects[0].is_infinite:
            rects = pagina.get_image_rects(item[0])
        for r in rects:
            # Ignorar imágenes que cubren casi toda la página (fondos, marcas de agua).
            if r.width * r.height < 0.5 * area_pagina:
                imagenes.append((Caja(r.x0, r.y0, r.x1, r.y1), _cargador_imagen(pagina.parent, item[0])))

    def recortar(caja: Caja, dpi: int) -> Image.Image:
        pix = pagina.get_pixmap(clip=fitz.Rect(caja.x0, caja.y0, caja.x1, caja.y1), dpi=dpi, colorspace=fitz.csGRAY)
        return Image.frombytes("L", (pix.width, pix.height), pix.samples)

    return Layout(numero, palabras, pagina.rect.width, pagina.rect.height, "digital", imagenes, recortar)


def _layout_ocr(imagen: Image.Image, palabras_ocr: list[ocr.Palabra], numero: int, escala: float) -> Layout:
    """Página leída por OCR. ``escala`` = píxeles por unidad de la plantilla (DPI/72 en un PDF, 1 en fotos)."""
    palabras = [
        parte
        for p in palabras_ocr
        for parte in partir_palabra(
            PalabraLayout(Caja(p.x / escala, p.y / escala, (p.x + p.w) / escala, (p.y + p.h) / escala), p.texto, p.conf))
    ]
    gris = imagen.convert("L")

    def recortar(caja: Caja, _dpi: int) -> Image.Image:
        return gris.crop((int(caja.x0 * escala), int(caja.y0 * escala), int(caja.x1 * escala), int(caja.y1 * escala)))

    return Layout(numero, palabras, imagen.width / escala, imagen.height / escala, "ocr", [], recortar)


class DocumentoLayout:
    """Páginas de un documento listas para leer por zonas. Usar con ``with``."""

    def __init__(self, ruta: Path, mime: str, texto: TextoDocumento):
        self._doc = None
        self.paginas: list[Layout] = []
        if mime == "application/pdf":
            self._doc = fitz.open(ruta)
            for i in range(len(texto.paginas)):
                if i in texto.imagenes_ocr:
                    self.paginas.append(
                        _layout_ocr(texto.imagenes_ocr[i], texto.palabras_ocr.get(i, []), i + 1, DPI_OCR / 72))
                else:
                    self.paginas.append(_layout_pdf_digital(self._doc[i], i + 1))
        elif 0 in texto.imagenes_ocr:
            self.paginas.append(_layout_ocr(texto.imagenes_ocr[0], texto.palabras_ocr.get(0, []), 1, 1.0))

    def __enter__(self) -> "DocumentoLayout":
        return self

    def __exit__(self, *exc: Any) -> None:
        if self._doc is not None:
            self._doc.close()


# ----------------------------------------------------------------------------
# Anclas
# ----------------------------------------------------------------------------
def _token(texto: str) -> str:
    """Forma comparable de una palabra: minúsculas, sin acentos ni puntuación (conserva paréntesis)."""
    return re.sub(r"[^\w()]", "", tu.quitar_acentos(texto.translate(_INVISIBLES)).casefold().replace("_", ""))


def _coincide(token_ancla: str, palabra: str) -> bool:
    t = _token(palabra)
    if _RE_MARCA.match(token_ancla):  # "(5)" puede venir pegado: "Dependencia:(5)" o "____(11)____"
        return token_ancla in t
    return t == token_ancla


def _subcaja(p: PalabraLayout, token: str) -> Caja:
    """Caja aproximada de ``token`` dentro de una palabra más larga (proporcional a los caracteres)."""
    crudo = tu.quitar_acentos(p.texto).casefold()
    i = crudo.find(token)
    if i < 0 or len(crudo) == 0:
        return p.caja
    ancho = p.caja.x1 - p.caja.x0
    return Caja(p.caja.x0 + ancho * i / len(crudo), p.caja.y0,
                p.caja.x0 + ancho * (i + len(token)) / len(crudo), p.caja.y1)


def buscar_ancla(layout: Layout, frases: list[str], region: Caja | None = None) -> Caja | None:
    """Primera aparición (en orden de lectura) de alguna de las frases, dentro de ``region`` si se da."""
    palabras = _orden_lectura([p for p in layout.palabras if region is None or region.contiene_centro(p.caja)])
    for frase in frases:
        tokens = [_token(t) for t in frase.split()]
        tokens = [t for t in tokens if t]
        if not tokens:
            continue
        for i in range(len(palabras) - len(tokens) + 1):
            grupo = palabras[i: i + len(tokens)]
            if all(_coincide(t, p.texto) for t, p in zip(tokens, grupo)):
                if len(tokens) == 1 and _RE_MARCA.match(tokens[0]):
                    return _subcaja(grupo[0], tokens[0])
                caja = grupo[0].caja
                for p in grupo[1:]:
                    caja = caja.union(p.caja)
                return caja
    return None


# ----------------------------------------------------------------------------
# Zonas
# ----------------------------------------------------------------------------
def calcular_zona(layout: Layout, spec: dict[str, Any]) -> tuple[Caja, Caja] | None:
    """Devuelve (zona_de_palabras, zona_de_recorte) o None si no se encontró el ancla.

    La zona de recorte es un poco más alta: los valores pegados como imagen
    suelen sobresalir de la línea.
    """
    ancla = buscar_ancla(layout, spec["ancla"])
    if ancla is None:
        return None
    h = ancla.h
    modo = spec.get("modo", "derecha")

    if modo == "derecha":
        banda = Caja(ancla.x1, ancla.y0 - 0.6 * h, layout.ancho, ancla.y1 + 0.6 * h)
        x1 = layout.ancho * MARGEN_DER
        if spec.get("hasta"):
            fin = buscar_ancla(layout, spec["hasta"], region=banda)
            if fin is not None:
                x1 = fin.x0 - 0.2 * h
        # Banda centrada en el ancla: lo que está en la misma línea tiene su centro a menos de
        # media altura; las etiquetas impresas debajo ("Apellido Paterno") quedan fuera.
        zona = Caja(ancla.x1 + 0.1 * h, ancla.cy - 0.5 * h, x1, ancla.cy + 0.5 * h)
        recorte = Caja(zona.x0, ancla.y0 - 0.65 * h, zona.x1, ancla.y1 + 0.65 * h)
        return zona, recorte

    if modo == "debajo":
        if "ancho" in spec:
            x0, x1 = ancla.x0 - 0.5 * h, ancla.x0 + spec["ancho"] * h
        else:
            x0, x1 = layout.ancho * MARGEN_IZQ, layout.ancho * MARGEN_DER
        y0 = ancla.y1 + 0.1 * h
        y1 = ancla.y1 + spec.get("alto", 12) * h
        if spec.get("hasta"):
            fin = buscar_ancla(layout, spec["hasta"], region=Caja(0, ancla.y1, layout.ancho, layout.alto))
            if fin is not None:
                y1 = fin.y0 - 0.1 * h
        zona = Caja(x0, y0, x1, y1)
        return zona, zona

    if modo == "caja":  # desplazamientos en alturas del ancla, relativos a sus bordes
        zona = Caja(ancla.x0 + spec.get("x0", 0) * h, ancla.y0 + spec.get("y0", 0) * h,
                    ancla.x1 + spec.get("x1", 0) * h, ancla.y1 + spec.get("y1", 0) * h)
        return zona, zona

    raise ValueError(f"Modo de zona desconocido: {modo}")


def _lineas(palabras: list[PalabraLayout]) -> list[list[PalabraLayout]]:
    """Agrupa palabras en renglones por cercanía vertical; cada renglón queda ordenado de izquierda a derecha."""
    if not palabras:
        return []
    alto = statistics.median(p.caja.h for p in palabras)
    lineas: list[list[PalabraLayout]] = []
    for p in sorted(palabras, key=lambda p: p.caja.cy):
        if lineas and abs(p.caja.cy - statistics.mean(q.caja.cy for q in lineas[-1])) <= 0.5 * alto:
            lineas[-1].append(p)
        else:
            lineas.append([p])
    return [sorted(l, key=lambda p: p.caja.x0) for l in lineas]


def _orden_lectura(palabras: list[PalabraLayout]) -> list[PalabraLayout]:
    return [p for linea in _lineas(palabras) for p in linea]


def _ensamblar(palabras: list[PalabraLayout]) -> str:
    """Une palabras en líneas (por cercanía vertical) y las líneas con saltos."""
    return "\n".join(" ".join(p.texto for p in linea) for linea in _lineas(palabras))


def limpiar_valor(texto: str) -> str:
    """Quita guiones bajos, marcas "(n)" y signos sueltos que deja el formato."""
    salida = []
    for linea in texto.translate(_INVISIBLES).splitlines():
        linea = _RE_MARCA_EN_TEXTO.sub(" ", linea.replace("_", " ").replace("|", " "))
        linea = re.sub(r"\s+", " ", linea).strip(" :;,.-")
        if linea:
            salida.append(linea)
    return "\n".join(salida)


@dataclass
class Lectura:
    texto: str | None
    confianza: float  # 0-1
    fuente: str  # texto_digital | ocr_zona | ocr
    ilegible: str | None = None  # motivo si el valor existe pero no se pudo leer


ALTO_MIN_OCR = 64  # px; las imágenes pegadas suelen venir a 96 dpi y se amplían antes del OCR


def _ocr_imagen_incrustada(caja: Caja, cargar: Callable[[], Image.Image | None], layout: Layout,
                           multilinea: bool) -> PalabraLayout | None:
    imagen = cargar() or layout.recorte(caja, DPI_ZONA_OCR)
    if imagen is None:
        return None
    if imagen.height < ALTO_MIN_OCR:
        f = ALTO_MIN_OCR * 1.5 / imagen.height
        imagen = imagen.resize((int(imagen.width * f), int(imagen.height * f)), Image.LANCZOS)
    texto, conf = ocr.ocr_zona(imagen, multilinea=multilinea)
    texto = " ".join(texto.split())
    return PalabraLayout(caja, texto, conf) if texto else None


_RE_CASILLA_VACIA = re.compile(r"^[\(\[]\s*[\)\]]$")


def _casillas_por_tinta(layout: Layout, palabras: list[PalabraLayout]) -> list[PalabraLayout]:
    """En escaneos el OCR suele "comerse" la x de una casilla ("( )" o "(x)" salen como "()").

    Se mide la tinta ENTRE los paréntesis: si hay, la casilla se marca como "(x)".
    """
    salida = []
    for p in palabras:
        if _RE_CASILLA_VACIA.match(p.texto.replace(" ", "")):
            w, h = p.caja.x1 - p.caja.x0, p.caja.h
            interior = Caja(p.caja.x0 + 0.3 * w, p.caja.y0 + 0.2 * h, p.caja.x1 - 0.3 * w, p.caja.y1 - 0.2 * h)
            img = layout.recorte(interior, DPI_ZONA_FIRMA)
            if img is not None and img.width and img.height and (np.asarray(img) < 140).mean() > 0.08:
                p = PalabraLayout(p.caja, "(x)", p.conf)
        salida.append(p)
    return salida


def leer_zona(layout: Layout, zona: Caja, recorte: Caja, multilinea: bool, casillas: bool = False) -> Lectura:
    """Lee el valor de una zona.

    * Página escaneada/foto: se usan las palabras del OCR de la página.
    * PDF digital: se usan las palabras digitales de la zona y, si hay imágenes
      pegadas en ella, se les hace OCR y se intercalan por posición (así
      "15 mes julio año 2026" se arma con números en imagen y "mes"/"año" en texto).
    """
    palabras = [p for p in layout.palabras if zona.contiene_centro(p.caja)]
    if layout.origen == "ocr":
        if casillas:
            palabras = _casillas_por_tinta(layout, palabras)
        texto = limpiar_valor(_ensamblar(palabras))
        conf = statistics.mean(p.conf for p in palabras) / 100 if palabras else 0.0
        return Lectura(texto or None, round(conf, 3), "ocr")

    imagenes = layout.imagenes_en(zona)
    if not imagenes:
        texto = limpiar_valor(_ensamblar(palabras))
        return Lectura(texto or None, 1.0, "texto_digital")
    if not ocr.ocr_disponible():
        texto = limpiar_valor(_ensamblar(palabras))
        return Lectura(texto or None, 1.0, "texto_digital",
                       ilegible="el dato está como imagen dentro del PDF y el OCR (Tesseract) no está instalado")
    leidas = [p for c, f in imagenes if (p := _ocr_imagen_incrustada(c, f, layout, multilinea))]
    texto = limpiar_valor(_ensamblar(palabras + leidas))
    if not leidas:
        return Lectura(texto or None, 1.0, "texto_digital",
                       ilegible="hay una imagen en el espacio del dato pero no se pudo leer")
    conf = min(p.conf for p in leidas) / 100
    return Lectura(texto or None, round(conf, 3), "ocr_zona")


# ----------------------------------------------------------------------------
# Campos
# ----------------------------------------------------------------------------
def _separar_cargo(texto: str) -> tuple[str, str | None]:
    """'Ing. Juan Pérez\\nJefe del centro de cómputo' -> ('Ing. Juan Pérez', 'Jefe del centro de cómputo')."""
    lineas = texto.splitlines()
    for i, linea in enumerate(lineas):
        primera = tu.normalizar_texto(linea).split()[:1]
        if i > 0 and primera and primera[0] in _CARGOS:
            return " ".join(lineas[:i]), " ".join(lineas[i:])
    return " ".join(lineas), None


def _opciones_marcadas(texto: str) -> list[str]:
    """Opciones con "(x)" en una lista de casillas: "( ) A (x) B" -> ["B"]."""
    plano = " ".join(texto.split())
    marcadas = re.findall(r"\(\s*[xX✓✔×*•]\s*\)\s*([^()]+?)(?=\s*\(|$)", plano)
    return [m.strip(" ,;.") for m in marcadas if m.strip(" ,;.")]


def _campo_desde_lectura(spec: dict[str, Any], lectura: Lectura, pagina: int) -> Campo:
    tipo = spec["tipo"]
    if not lectura.texto:
        return Campo(pagina=pagina, fuente=lectura.fuente, ilegible=bool(lectura.ilegible), error=lectura.ilegible)
    if tipo == "opcion":
        marcadas = _opciones_marcadas(lectura.texto)
        return Campo(crudo=marcadas or None, valor=marcadas, normalizado=[tu.normalizar_texto(m) for m in marcadas],
                     valido=len(marcadas) == 1, confianza=lectura.confianza, fuente=lectura.fuente, pagina=pagina,
                     error=None if len(marcadas) <= 1 else "hay más de una opción marcada")
    if tipo == "parrafo":
        plano = tu.limpiar_espacios(lectura.texto.replace("\n", " "))
        return Campo(crudo=plano, valor=plano, normalizado=tu.normalizar_texto(plano), valido=bool(plano),
                     confianza=lectura.confianza, fuente=lectura.fuente, pagina=pagina)
    crudo = tu.limpiar_espacios(lectura.texto.replace("\n", " "))
    campo = _construir(tipo, crudo, lectura.confianza, pagina)
    campo.fuente = lectura.fuente
    return campo


def extraer_por_zonas(docl: DocumentoLayout, cfg_campos: dict[str, dict[str, Any]]) -> dict[str, Campo]:
    """Lee cada campo de su zona, buscando el ancla en las páginas en orden."""
    resultado: dict[str, Campo] = {}
    for nombre, spec in cfg_campos.items():
        if nombre in resultado:  # ya lo llenó otro campo (p. ej. el cargo bajo un nombre)
            continue
        campo = Campo()
        if "zona" not in spec:  # se llena desde otro campo (separar_cargo)
            continue
        for layout in docl.paginas:
            zonas = calcular_zona(layout, spec["zona"])
            if zonas is None:
                continue
            multilinea = spec["zona"].get("modo") == "debajo"
            lectura = leer_zona(layout, zonas[0], zonas[1], multilinea, casillas=spec["tipo"] == "opcion")
            separar = spec.get("separar_cargo")
            if separar and lectura.texto:
                nombre_txt, cargo_txt = _separar_cargo(lectura.texto)
                if separar in cfg_campos:
                    resultado[separar] = _campo_desde_lectura(
                        cfg_campos[separar], Lectura(cargo_txt, lectura.confianza, lectura.fuente), layout.numero)
                lectura = Lectura(nombre_txt, lectura.confianza, lectura.fuente)
            campo = _campo_desde_lectura(spec, lectura, layout.numero)
            break
        resultado[nombre] = campo
    for nombre in cfg_campos:  # campos sin zona propia que no se llenaron
        resultado.setdefault(nombre, Campo())
    return {k: resultado[k] for k in cfg_campos}


# ----------------------------------------------------------------------------
# Firmas y sellos
# ----------------------------------------------------------------------------
def detectar_firmas_por_zonas(docl: DocumentoLayout, firmas_cfg: list[dict[str, Any]], umbral: float) -> list[ResultadoFirma]:
    resultados = []
    for spec in firmas_cfg:
        res = ResultadoFirma(id=spec["id"], etiqueta=spec["etiqueta"], evaluable=False,
                             motivo=f"No se encontró en el formato el espacio de «{spec['etiqueta']}».")
        for layout in docl.paginas:
            zonas = calcular_zona(layout, spec["zona"])
            if zonas is None:
                continue
            zona = zonas[0]
            dpi = DPI_ZONA_FIRMA
            imagen = layout.recorte(zona, dpi)
            if imagen is None:
                break
            gris = np.asarray(imagen.convert("L"), dtype=np.uint8)
            ex = gris.shape[1] / max(zona.x1 - zona.x0, 1e-6)
            ey = gris.shape[0] / max(zona.y1 - zona.y0, 1e-6)
            mascaras = []
            for p in layout.palabras:  # texto impreso dentro de la zona ("(8)", "SELLO", la línea)
                if p.caja.intersecta(zona) and p.conf >= 70:
                    mascaras.append((int((p.caja.x0 - zona.x0) * ex) - 2, int((p.caja.y0 - zona.y0) * ey) - 2,
                                     int((p.caja.x1 - zona.x0) * ex) + 2, int((p.caja.y1 - zona.y0) * ey) + 2))
            densidad, cobertura = medir_tinta(gris, mascaras)
            detectada = densidad >= umbral and cobertura >= COBERTURA_MIN_X
            res = ResultadoFirma(id=spec["id"], etiqueta=spec["etiqueta"], evaluable=True, detectada=detectada,
                                 densidad=round(densidad, 5), cobertura_x=round(cobertura, 3), pagina=layout.numero)
            break
        resultados.append(res)
    return resultados
