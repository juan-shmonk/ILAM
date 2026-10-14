"""Obtención de texto desde PDF (texto digital u OCR) e imágenes."""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf as fitz  # PyMuPDF
import numpy as np
from PIL import Image

from app.config import get_settings
from app.services.analysis import ocr

DPI_OCR = 200
# Una página con menos caracteres que esto se considera "sin texto digital" (escaneo).
MIN_CHARS_PAGINA_DIGITAL = 25


class ArchivoNoLegible(Exception):
    """El archivo no se pudo abrir (corrupto, protegido con contraseña, etc.)."""


@dataclass
class TextoDocumento:
    paginas: list[str]
    n_paginas: int
    metodo: str  # texto_digital | ocr | mixto | ninguno
    confianza_ocr: float | None = None  # 0-100, solo si hubo OCR
    ocr_disponible: bool = False
    nitidez: float | None = None  # varianza del laplaciano (solo imágenes/OCR)
    avisos: list[str] = field(default_factory=list)
    # Palabras OCR por página (0-index) y dimensión de la imagen usada, para localizar firmas.
    palabras_ocr: dict[int, list[ocr.Palabra]] = field(default_factory=dict)
    imagenes_ocr: dict[int, Image.Image] = field(default_factory=dict)

    @property
    def texto(self) -> str:
        return "\n".join(self.paginas)

    @property
    def total_caracteres(self) -> int:
        return sum(len("".join(p.split())) for p in self.paginas)


def nitidez(imagen: Image.Image) -> float:
    """Varianza del laplaciano: valores bajos indican imagen borrosa."""
    gris = np.asarray(imagen.convert("L").resize((800, int(800 * imagen.height / imagen.width))), dtype=np.float32)
    lap = 4 * gris[1:-1, 1:-1] - gris[:-2, 1:-1] - gris[2:, 1:-1] - gris[1:-1, :-2] - gris[1:-1, 2:]
    return float(lap.var())


def _pixmap_a_imagen(pix: fitz.Pixmap) -> Image.Image:
    return Image.open(io.BytesIO(pix.tobytes("png")))


def extraer_texto(ruta: Path, mime: str) -> TextoDocumento:
    settings = get_settings()
    if mime == "application/pdf":
        return _extraer_pdf(ruta, settings.max_paginas)
    return _extraer_imagen(ruta)


def _extraer_pdf(ruta: Path, max_paginas: int) -> TextoDocumento:
    try:
        doc = fitz.open(ruta)
    except Exception as exc:  # archivo corrupto
        raise ArchivoNoLegible(f"No se pudo abrir el PDF: {exc}") from exc
    if doc.needs_pass:
        raise ArchivoNoLegible("El PDF está protegido con contraseña.")

    n_paginas = doc.page_count
    resultado = TextoDocumento(paginas=[], n_paginas=n_paginas, metodo="ninguno", ocr_disponible=ocr.ocr_disponible())
    usados_digital = usados_ocr = 0
    confs: list[float] = []

    for i in range(min(n_paginas, max_paginas)):
        pagina = doc[i]
        texto = pagina.get_text("text") or ""
        if len("".join(texto.split())) >= MIN_CHARS_PAGINA_DIGITAL:
            resultado.paginas.append(texto)
            usados_digital += 1
            continue
        # Página sin texto digital: escaneo o foto dentro de un PDF.
        if resultado.ocr_disponible:
            pix = pagina.get_pixmap(matrix=fitz.Matrix(DPI_OCR / 72, DPI_OCR / 72), colorspace=fitz.csRGB)
            imagen = _pixmap_a_imagen(pix)
            pag_ocr = ocr.ocr_imagen(imagen)
            resultado.paginas.append(pag_ocr.texto)
            resultado.palabras_ocr[i] = pag_ocr.palabras
            resultado.imagenes_ocr[i] = imagen
            if pag_ocr.palabras:  # una página en blanco no debe bajar la confianza global
                confs.append(pag_ocr.confianza)
            usados_ocr += 1
            if resultado.nitidez is None:
                resultado.nitidez = nitidez(imagen)
        else:
            resultado.paginas.append("")
            resultado.avisos.append(f"La página {i + 1} no tiene texto digital y el OCR no está instalado.")
    if n_paginas > max_paginas:
        resultado.avisos.append(f"Solo se analizaron las primeras {max_paginas} páginas.")

    if usados_digital and usados_ocr:
        resultado.metodo = "mixto"
    elif usados_ocr:
        resultado.metodo = "ocr"
    elif usados_digital:
        resultado.metodo = "texto_digital"
    resultado.confianza_ocr = sum(confs) / len(confs) if confs else None
    doc.close()
    return resultado


def _extraer_imagen(ruta: Path) -> TextoDocumento:
    try:
        imagen = Image.open(ruta)
        imagen.load()
    except Exception as exc:
        raise ArchivoNoLegible(f"No se pudo abrir la imagen: {exc}") from exc
    resultado = TextoDocumento(paginas=[""], n_paginas=1, metodo="ninguno", ocr_disponible=ocr.ocr_disponible())
    if not resultado.ocr_disponible:
        resultado.avisos.append("Para leer imágenes se necesita Tesseract OCR, que no está instalado.")
        return resultado
    imagen = imagen.convert("RGB")
    pag_ocr = ocr.ocr_imagen(imagen)
    resultado.paginas = [pag_ocr.texto]
    resultado.palabras_ocr[0] = pag_ocr.palabras
    resultado.imagenes_ocr[0] = imagen
    resultado.metodo = "ocr"
    resultado.confianza_ocr = pag_ocr.confianza
    resultado.nitidez = nitidez(imagen)
    return resultado
