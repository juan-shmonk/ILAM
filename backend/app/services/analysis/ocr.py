"""OCR opcional con Tesseract.

Si Tesseract no está instalado, el sistema sigue funcionando con PDF de texto
digital; para fotos o escaneos avisa que no pudo leerlos en vez de fallar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

from PIL import Image, ImageOps

from app.config import get_settings


@dataclass
class Palabra:
    texto: str
    x: int
    y: int
    w: int
    h: int
    conf: float


@dataclass
class PaginaOcr:
    texto: str
    palabras: list[Palabra] = field(default_factory=list)
    confianza: float = 0.0  # 0-100


@lru_cache
def _configurar() -> tuple[bool, str | None]:
    """Devuelve (disponible, idioma_a_usar)."""
    try:
        import pytesseract
    except ImportError:
        return False, None
    settings = get_settings()
    if settings.tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd
    try:
        pytesseract.get_tesseract_version()
        idiomas = set(pytesseract.get_languages(config=""))
    except Exception:
        return False, None
    if settings.ocr_lang in idiomas:
        return True, settings.ocr_lang
    if "eng" in idiomas:  # sin acentos, pero mejor que nada
        return True, "eng"
    return False, None


def ocr_disponible() -> bool:
    return _configurar()[0]


def idioma_ocr() -> str | None:
    return _configurar()[1]


def ocr_imagen(imagen: Image.Image) -> PaginaOcr:
    """Ejecuta OCR sobre una imagen y reconstruye texto por líneas."""
    import pytesseract
    from pytesseract import Output

    disponible, idioma = _configurar()
    if not disponible:
        raise RuntimeError("Tesseract no está disponible")

    gris = ImageOps.autocontrast(imagen.convert("L"))
    datos = pytesseract.image_to_data(gris, lang=idioma, output_type=Output.DICT)

    lineas: dict[tuple[int, int, int], list[str]] = {}
    palabras: list[Palabra] = []
    confs: list[float] = []
    for i, texto in enumerate(datos["text"]):
        texto = (texto or "").strip()
        try:
            conf = float(datos["conf"][i])
        except (TypeError, ValueError):
            conf = -1
        if not texto or conf < 0:
            continue
        clave = (datos["block_num"][i], datos["par_num"][i], datos["line_num"][i])
        lineas.setdefault(clave, []).append(texto)
        confs.append(conf)
        palabras.append(
            Palabra(texto, datos["left"][i], datos["top"][i], datos["width"][i], datos["height"][i], conf)
        )
    texto_final = "\n".join(" ".join(ws) for _, ws in sorted(lineas.items()))
    confianza = sum(confs) / len(confs) if confs else 0.0
    return PaginaOcr(texto=texto_final, palabras=palabras, confianza=confianza)
