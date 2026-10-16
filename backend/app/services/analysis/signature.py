"""Detección de *presencia* de firma (no de autenticidad).

Método: se localiza el texto de la etiqueta ("Firma del responsable"), se mira
la zona justo encima y se mide cuánta "tinta" hay, ignorando las líneas
horizontales y el texto impreso. Es una heurística: puede fallar con firmas muy
claras o fotos con sombras, por eso el resultado es una observación, no un error.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import pymupdf as fitz
import numpy as np
from PIL import Image

from app.services.analysis import textutil as tu
from app.services.analysis.ocr import Palabra
from app.services.analysis.text_extraction import TextoDocumento

DPI_FIRMA = 150
ALTO_ZONA_EN_ALTURAS_DE_ETIQUETA = 6.0
UMBRAL_OSCURO = 140
UMBRAL_LINEA = 0.55  # una fila con más de este % de píxeles oscuros es una línea, no firma
COBERTURA_MIN_X = 0.10  # la tinta debe extenderse al menos por este % del ancho


@dataclass
class ResultadoFirma:
    id: str
    etiqueta: str
    evaluable: bool  # False si no se pudo localizar la etiqueta o evaluar
    detectada: bool | None = None
    densidad: float | None = None
    cobertura_x: float | None = None
    pagina: int | None = None  # 1-indexada
    motivo: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def medir_tinta(gris: np.ndarray, mascaras: list[tuple[int, int, int, int]]) -> tuple[float, float]:
    """Devuelve (densidad, cobertura_x) de tinta en la zona, sin líneas ni texto impreso.

    Se descartan las filas y columnas casi completamente oscuras: son la línea
    de firma y los bordes de las tablas del formato, no tinta del firmante.
    """
    zona = gris.copy()
    for x0, y0, x1, y1 in mascaras:  # blanquear texto impreso
        zona[max(y0, 0): max(y1, 0), max(x0, 0): max(x1, 0)] = 255
    oscuro = zona < UMBRAL_OSCURO
    filas_linea = oscuro.mean(axis=1) > UMBRAL_LINEA
    oscuro[filas_linea, :] = False  # quitar líneas horizontales (la línea de firma)
    columnas_linea = oscuro.mean(axis=0) > UMBRAL_LINEA
    oscuro[:, columnas_linea] = False  # quitar líneas verticales (bordes de tabla)
    if oscuro.size == 0:
        return 0.0, 0.0
    densidad = float(oscuro.mean())
    cobertura = float(oscuro.any(axis=0).mean())
    return densidad, cobertura


def _zona_desde_etiqueta(x0: float, y0: float, x1: float, y1: float) -> tuple[float, float, float, float]:
    alto_etiqueta = max(y1 - y0, 1.0)
    ancho = x1 - x0
    return (
        x0 - 0.3 * ancho,
        y0 - ALTO_ZONA_EN_ALTURAS_DE_ETIQUETA * alto_etiqueta,
        x1 + 0.3 * ancho,
        y0 - 1.0,
    )


def _firma_pdf_digital(pagina: fitz.Page, etiqueta: str, umbral: float) -> tuple[bool, ResultadoFirma] | None:
    rects = pagina.search_for(etiqueta)
    if not rects:
        return None
    r = rects[0]
    zx0, zy0, zx1, zy1 = _zona_desde_etiqueta(r.x0, r.y0, r.x1, r.y1)
    clip = fitz.Rect(zx0, zy0, zx1, zy1) & pagina.rect
    escala = DPI_FIRMA / 72
    pix = pagina.get_pixmap(matrix=fitz.Matrix(escala, escala), clip=clip, colorspace=fitz.csGRAY)
    gris = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    mascaras = []
    for w in pagina.get_text("words", clip=clip):  # texto impreso dentro de la zona
        mascaras.append(
            (int((w[0] - clip.x0) * escala) - 1, int((w[1] - clip.y0) * escala) - 1,
             int((w[2] - clip.x0) * escala) + 2, int((w[3] - clip.y0) * escala) + 2)
        )
    densidad, cobertura = medir_tinta(gris, mascaras)
    detectada = densidad >= umbral and cobertura >= COBERTURA_MIN_X
    return detectada, ResultadoFirma(
        id="", etiqueta=etiqueta, evaluable=True, detectada=detectada,
        densidad=round(densidad, 5), cobertura_x=round(cobertura, 3),
    )


def _buscar_etiqueta_ocr(palabras: list[Palabra], etiqueta: str) -> tuple[int, int, int, int] | None:
    objetivo = tu.normalizar_texto(etiqueta).split()
    normal = [tu.normalizar_texto(p.texto) for p in palabras]
    n = len(objetivo)
    for i in range(len(palabras) - n + 1):
        if normal[i: i + n] == objetivo:
            grupo = palabras[i: i + n]
            x0 = min(p.x for p in grupo)
            y0 = min(p.y for p in grupo)
            x1 = max(p.x + p.w for p in grupo)
            y1 = max(p.y + p.h for p in grupo)
            return x0, y0, x1, y1
    return None


def _firma_ocr(imagen: Image.Image, palabras: list[Palabra], etiqueta: str, umbral: float) -> ResultadoFirma | None:
    caja = _buscar_etiqueta_ocr(palabras, etiqueta)
    if caja is None:
        return None
    zx0, zy0, zx1, zy1 = (int(v) for v in _zona_desde_etiqueta(*caja))
    zx0, zy0 = max(zx0, 0), max(zy0, 0)
    zx1, zy1 = min(zx1, imagen.width), min(zy1, imagen.height)
    if zx1 <= zx0 or zy1 <= zy0:
        return None
    gris = np.asarray(imagen.convert("L").crop((zx0, zy0, zx1, zy1)), dtype=np.uint8)
    mascaras = []
    for p in palabras:  # texto impreso reconocido con buena confianza
        if p.conf >= 70:
            mascaras.append((p.x - zx0 - 1, p.y - zy0 - 1, p.x + p.w - zx0 + 2, p.y + p.h - zy0 + 2))
    densidad, cobertura = medir_tinta(gris, mascaras)
    detectada = densidad >= umbral and cobertura >= COBERTURA_MIN_X
    return ResultadoFirma(
        id="", etiqueta=etiqueta, evaluable=True, detectada=detectada,
        densidad=round(densidad, 5), cobertura_x=round(cobertura, 3),
    )


def detectar_firmas(ruta, texto: TextoDocumento, firmas_cfg: list[dict], umbral: float) -> list[ResultadoFirma]:
    """Evalúa cada firma definida para el tipo de documento."""
    resultados: list[ResultadoFirma] = []
    doc = None
    try:
        if str(ruta).lower().endswith(".pdf"):
            doc = fitz.open(ruta)
    except Exception:
        doc = None

    for spec in firmas_cfg:
        res: ResultadoFirma | None = None
        for i in range(texto.n_paginas if texto.n_paginas else 0):
            if i >= len(texto.paginas):
                break
            if i in texto.imagenes_ocr:  # página leída por OCR
                res = _firma_ocr(texto.imagenes_ocr[i], texto.palabras_ocr[i], spec["etiqueta"], umbral)
            elif doc is not None:
                encontrado = _firma_pdf_digital(doc[i], spec["etiqueta"], umbral)
                res = encontrado[1] if encontrado else None
            if res is not None:
                res.pagina = i + 1
                break
        if res is None:
            res = ResultadoFirma(
                id=spec["id"], etiqueta=spec["etiqueta"], evaluable=False,
                motivo=f"No se encontró el texto «{spec['etiqueta']}» para ubicar la firma.",
            )
        res.id = spec["id"]
        resultados.append(res)
    if doc is not None:
        doc.close()
    return resultados
