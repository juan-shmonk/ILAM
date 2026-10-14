"""Prevalidación de archivos sueltos, sin base de datos ni API.

La usan el evaluador y las pruebas; también sirve para probar rápido desde la
línea de comandos.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.analysis.pipeline import analizar_documento
from app.services.report import construir_reporte
from app.services.storage import detectar_mime_archivo


def prevalidar_archivos(archivos: dict[str, Path], tramite: str = "servicio_social") -> dict[str, Any]:
    """``archivos``: {tipo_de_documento: ruta}. Devuelve el reporte completo."""
    docs = []
    for i, (tipo, ruta) in enumerate(archivos.items(), start=1):
        mime = detectar_mime_archivo(ruta) or "application/octet-stream"
        resultado = analizar_documento(ruta, mime, tipo)
        docs.append({"id": i, "tipo": tipo, "version": 1, "nombre_original": ruta.name,
                     "resultado": resultado.to_dict()})
    return construir_reporte(0, tramite, docs)
