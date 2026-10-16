"""Pipeline de análisis de un documento: texto -> formato -> campos -> firmas.

No decide si algo está bien o mal; solo produce datos estructurados. Las
decisiones (errores/advertencias) las toma el motor de reglas.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services import catalogo
from app.services.analysis import textutil as tu
from app.services.analysis import plantilla
from app.services.analysis.extractors import extraer_campos
from app.services.analysis.signature import detectar_firmas
from app.services.analysis.text_extraction import ArchivoNoLegible, extraer_texto


@dataclass
class ResultadoDocumento:
    tipo: str
    calidad: dict[str, Any]
    formato: dict[str, Any]
    campos: dict[str, dict[str, Any]]
    firmas: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {"tipo": self.tipo, "calidad": self.calidad, "formato": self.formato,
                "campos": self.campos, "firmas": self.firmas}


def clasificar(texto: str) -> str | None:
    """Detecta qué tipo de documento parece ser, según los títulos configurados.

    Devuelve el código del tipo cuyo título aparece primero en el texto.
    """
    normal = tu.normalizar_texto(texto)
    mejor: tuple[int, str] | None = None
    for codigo in catalogo.tipos_documento():
        for cfg in catalogo.formatos(codigo):
            for titulo in cfg["titulos"]:
                pos = normal.find(tu.normalizar_texto(titulo))
                if pos >= 0 and (mejor is None or pos < mejor[0]):
                    mejor = (pos, codigo)
    return mejor[1] if mejor else None


def analizar_documento(ruta: Path, mime: str, tipo: str) -> ResultadoDocumento:
    cfg = catalogo.tipo(tipo)
    if cfg is None:
        raise ValueError(f"Tipo de documento desconocido: {tipo}")
    umbrales = catalogo.requisitos()["umbrales"]

    calidad: dict[str, Any] = {
        "metodo": "ninguno", "n_paginas": 0, "caracteres": 0, "confianza_ocr": None,
        "nitidez": None, "ocr_disponible": False, "legible": False, "motivo": None, "avisos": [],
    }
    formato: dict[str, Any] = {"esperado": tipo, "detectado": None, "coincide": False, "version": cfg["formato"]}

    try:
        texto = extraer_texto(ruta, mime)
    except ArchivoNoLegible as exc:
        calidad["motivo"] = str(exc)
        return ResultadoDocumento(tipo, calidad, formato, {}, [])

    calidad.update(
        metodo=texto.metodo, n_paginas=texto.n_paginas, caracteres=texto.total_caracteres,
        confianza_ocr=None if texto.confianza_ocr is None else round(texto.confianza_ocr, 1),
        nitidez=None if texto.nitidez is None else round(texto.nitidez, 1),
        ocr_disponible=texto.ocr_disponible, avisos=list(texto.avisos),
    )

    # --- Compuerta de legibilidad (R008) ---
    if texto.total_caracteres < umbrales["caracteres_min"]:
        if texto.metodo == "ninguno" and not texto.ocr_disponible:
            calidad["motivo"] = "El archivo es una imagen o escaneo y el OCR (Tesseract) no está instalado."
        else:
            calidad["motivo"] = "Casi no se pudo leer texto del documento."
    elif texto.confianza_ocr is not None and texto.confianza_ocr < umbrales["ocr_confianza_min"]:
        calidad["motivo"] = (
            f"La lectura tiene poca confianza ({texto.confianza_ocr:.0f}%): la imagen puede estar "
            "borrosa, oscura o inclinada."
        )
    else:
        calidad["legible"] = True

    if not calidad["legible"]:
        return ResultadoDocumento(tipo, calidad, formato, {}, [])

    # --- Formato esperado (R005) ---
    detectado = clasificar(texto.texto)
    formato["detectado"] = detectado
    formato["coincide"] = detectado == tipo
    # Versión del formato (oficial vigente, sintético de pruebas...) según el texto leído.
    cfg = catalogo.elegir_formato(tipo, texto.texto) or cfg
    formato["version"] = cfg["formato"]

    if cfg.get("extraccion") == "zonas":
        with plantilla.DocumentoLayout(ruta, mime, texto) as docl:
            campos_obj = plantilla.extraer_por_zonas(docl, cfg["campos"])
            firmas_obj = plantilla.detectar_firmas_por_zonas(docl, cfg.get("firmas", []), umbrales["tinta_firma_min"])
    else:
        confianza = 1.0 if texto.confianza_ocr is None else round(texto.confianza_ocr / 100, 3)
        campos_obj = extraer_campos(texto.paginas, cfg["campos"], confianza)
        firmas_obj = detectar_firmas(ruta, texto, cfg.get("firmas", []), umbrales["tinta_firma_min"])
    campos = {k: c.to_dict() for k, c in campos_obj.items()}
    firmas = [f.to_dict() for f in firmas_obj]
    return ResultadoDocumento(tipo, calidad, formato, campos, firmas)
