"""Generador de documentos SINTÉTICOS de servicio social con errores inyectados.

Crea, por cada escenario, una carpeta con los dos PDF del MVP (solicitud y plan de trabajo) y un
``ground_truth.json`` con la respuesta correcta (qué errores se inyectaron y
qué datos contiene cada documento). Sirve para:

  * probar el sistema sin datos reales de alumnos,
  * medir precisión y recall (scripts/evaluar.py),
  * mostrar a tus compañeros el formato de ``ground_truth.json`` para que
    creen documentos propios con el mismo esquema.

Uso (desde la carpeta backend/):
    python -m scripts.generar_muestras            # crea samples/
    python -m scripts.generar_muestras --salida otra_carpeta

Los datos son inventados. Cada PDF lleva el aviso "documento sintético".
"""

from __future__ import annotations

import argparse
import copy
import io
import json
import math
import random
import sys
import zlib
from datetime import date
from pathlib import Path
from typing import Any

import pymupdf as fitz
from PIL import Image, ImageFilter

from app.services.analysis import textutil as tu

AVISO_SINTETICO = "DOCUMENTO SINTETICO DE PRUEBA - NO ES UN DOCUMENTO OFICIAL"

BASE: dict[str, Any] = {
    "nombre": "Laura Beatriz Hernández Castillo",
    "matricula": "21530177",
    "carrera": "Ingeniería en Sistemas Computacionales",
    "institucion": "H. Ayuntamiento de Benito Juárez",
    "responsable": "Lic. María Fernanda Ruiz Torres",
    "cargo_responsable": "Directora de Vinculación",
    "fecha_inicio": "2027-02-15",
    "fecha_fin": "2027-08-15",
    "horas": 480,
    "actividades": [
        "Apoyo en el mantenimiento de equipos de cómputo de las oficinas.",
        "Elaboración de manuales de usuario para el sistema de atención ciudadana.",
        "Soporte técnico a usuarios y registro de incidencias en la mesa de ayuda.",
        "Respaldo periódico de información y revisión de la red local.",
    ],
}

# Campos que aparecen en cada documento (igual que en config_docs/*.json)
CAMPOS_POR_DOC = {
    "solicitud": ["nombre", "matricula", "carrera", "institucion", "fecha_inicio", "fecha_fin", "horas"],
    "plan_trabajo": ["nombre", "matricula", "carrera", "institucion", "responsable", "fecha_inicio",
                     "fecha_fin", "horas", "actividades"],
}
TITULOS = {
    "solicitud": "SOLICITUD DE SERVICIO SOCIAL",
    "plan_trabajo": "PLAN DE TRABAJO",
}
ETIQUETAS = {
    "solicitud": {"nombre": "Nombre del alumno", "matricula": "Matrícula", "carrera": "Carrera",
                  "institucion": "Institución receptora", "fecha_inicio": "Fecha de inicio",
                  "fecha_fin": "Fecha de término", "horas": "Total de horas"},
    "plan_trabajo": {"nombre": "Nombre del alumno", "matricula": "Matrícula", "carrera": "Carrera",
                     "institucion": "Institución receptora", "responsable": "Responsable",
                     "fecha_inicio": "Fecha de inicio", "fecha_fin": "Fecha de término",
                     "horas": "Total de horas", "actividades": "Actividades"},
}
# Firmas: (id, etiqueta)
FIRMAS_POR_DOC = {
    "solicitud": [("alumno", "Firma del alumno")],
    "plan_trabajo": [("alumno", "Firma del alumno"), ("responsable", "Firma del responsable")],
}
# Formato en que se escriben las fechas en cada documento (para probar el parser)
FORMATO_FECHA = {"solicitud": "num", "plan_trabajo": "texto"}
ARCHIVOS = {"solicitud": "solicitud.pdf", "plan_trabajo": "plan_trabajo.pdf"}


def _fecha_texto(iso: str, formato: str) -> str:
    d = date.fromisoformat(iso)
    if formato == "texto":
        return f"{d.day} de {tu.MESES_NOMBRE[d.month]} de {d.year}"
    return f"{d.day:02d}/{d.month:02d}/{d.year}"


def _valor_texto(campo: str, valor: Any, tipo_doc: str) -> str:
    if campo.startswith("fecha"):
        return _fecha_texto(valor, FORMATO_FECHA[tipo_doc])
    return str(valor)


# ----------------------------------------------------------------------------
# Dibujo de PDF
# ----------------------------------------------------------------------------
def _garabato(pagina: fitz.Page, x0: float, y_base: float, semilla: int) -> None:
    """Dibuja una firma simulada (trazo continuo) sobre la línea de firma."""
    rng = random.Random(semilla)
    puntos = []
    n = 60
    for i in range(n):
        t = i / (n - 1)
        x = x0 + 10 + t * 120
        y = y_base - 14 - 10 * math.sin(t * 9 + rng.random() * 0.5) - 8 * math.sin(t * 17) * rng.random()
        puntos.append(fitz.Point(x, y))
    forma = pagina.new_shape()
    forma.draw_polyline(puntos)
    forma.finish(color=(0.05, 0.05, 0.35), width=1.6, closePath=False)
    forma.commit()


def _bloque_firma(pagina: fitz.Page, x: float, y: float, etiqueta: str, firmado: bool, semilla: int) -> None:
    pagina.draw_line((x, y), (x + 160, y), color=(0, 0, 0), width=0.8)
    ancho = fitz.get_text_length(etiqueta, fontname="helv", fontsize=10)
    pagina.insert_text((x + (160 - ancho) / 2, y + 14), etiqueta, fontname="helv", fontsize=10)
    if firmado:
        _garabato(pagina, x, y, semilla)


def dibujar_documento(tipo: str, datos: dict[str, Any], firmas: dict[str, bool],
                      campos_omitidos: list[str] | None = None, paginas_extra: int = 0,
                      titulo: str | None = None) -> fitz.Document:
    omitidos = set(campos_omitidos or [])
    doc = fitz.open()
    pagina = doc.new_page(width=595, height=842)
    pagina.insert_text((72, 40), AVISO_SINTETICO, fontname="helv", fontsize=7, color=(0.5, 0.5, 0.5))
    pagina.insert_text((72, 80), "Servicio Social - Institución educativa (ejemplo)", fontname="helv", fontsize=10)
    pagina.insert_text((72, 120), titulo or TITULOS[tipo], fontname="hebo", fontsize=16)
    y = 165
    for campo in CAMPOS_POR_DOC[tipo]:
        if campo in omitidos:
            y += 26  # deja el hueco, como un campo en blanco
            continue
        etiqueta = ETIQUETAS[tipo][campo]
        if campo == "actividades":
            pagina.insert_text((72, y), f"{etiqueta}:", fontname="helv", fontsize=11)
            y += 20
            for n, act in enumerate(datos["actividades"], start=1):
                pagina.insert_text((90, y), f"{n}. {act}"[:95], fontname="helv", fontsize=10)
                y += 18
            y += 8
            continue
        pagina.insert_text((72, y), f"{etiqueta}: {_valor_texto(campo, datos[campo], tipo)}",
                           fontname="helv", fontsize=11)
        y += 26
    # Bloques de firma
    y_firma = 700
    specs = FIRMAS_POR_DOC[tipo]
    for i, (fid, etiqueta) in enumerate(specs):
        x = 72 if len(specs) == 1 or i == 0 else 340
        _bloque_firma(pagina, x, y_firma, etiqueta, firmas.get(fid, True), semilla=zlib.crc32(f"{tipo}:{fid}".encode()) % 1000)
    for _ in range(paginas_extra):
        doc.new_page(width=595, height=842)
    return doc


def _rasterizar(doc: fitz.Document, dpi: int = 200, borroso: bool = False, ruido: bool = True) -> fitz.Document:
    """Convierte un PDF de texto en un 'escaneo' (PDF con solo imágenes)."""
    salida = fitz.open()
    rng = random.Random(7)
    for pagina in doc:
        pix = pagina.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), colorspace=fitz.csRGB)
        img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("L")
        if borroso:
            img = img.resize((img.width // 6, img.height // 6)).filter(ImageFilter.GaussianBlur(2))
            img = img.resize((pix.width, pix.height))
        elif ruido:
            img = img.rotate(0.4, expand=False, fillcolor=255).filter(ImageFilter.GaussianBlur(0.6))
            pixeles = img.load()
            for _ in range(img.width * img.height // 400):  # sal y pimienta leve
                pixeles[rng.randrange(img.width), rng.randrange(img.height)] = rng.choice((0, 255))
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=80)
        nueva = salida.new_page(width=pagina.rect.width, height=pagina.rect.height)
        nueva.insert_image(nueva.rect, stream=buf.getvalue())
    return salida


# ----------------------------------------------------------------------------
# Escenarios: cada uno describe qué se altera y qué se espera que el sistema marque
# ----------------------------------------------------------------------------
# Claves de error esperadas (ver scripts/evaluar.py):
#   "<campo>"                        error de contenido en ese campo (en uno o entre documentos)
#   "firma:<id>@<documento>"         firma no detectada
#   "R005@<doc>", "R007@<doc>", "R008@<doc>"   formato, páginas o legibilidad del documento
ESCENARIOS: list[dict[str, Any]] = [
    {"id": "01_correcto", "descripcion": "Los dos documentos correctos y firmados.", "errores": [],
     "estado": "SIN_OBSERVACIONES"},
    {"id": "02_fecha_inicio_distinta", "descripcion": "La solicitud dice 10/02/2027 y el plan 15 de febrero de 2027.",
     "cambios": {"solicitud": {"fecha_inicio": "2027-02-10"}}, "errores": ["fecha_inicio"]},
    {"id": "03_matricula_distinta", "descripcion": "La matrícula del plan de trabajo no coincide con la de la solicitud.",
     "cambios": {"plan_trabajo": {"matricula": "21530717"}}, "errores": ["matricula"]},
    {"id": "04_sin_firma_responsable", "descripcion": "El plan de trabajo no tiene la firma del responsable.",
     "firmas": {"plan_trabajo": {"responsable": False}}, "errores": ["firma:responsable@plan_trabajo"]},
    {"id": "05_horas_incorrectas", "descripcion": "El plan de trabajo dice 300 horas en lugar de 480.",
     "cambios": {"plan_trabajo": {"horas": 300}}, "errores": ["horas"]},
    {"id": "06_campo_faltante", "descripcion": "La solicitud no tiene la carrera.",
     "omitir": {"solicitud": ["carrera"]}, "errores": ["carrera"]},
    {"id": "07_nombre_con_variante", "descripcion": "La solicitud escribe un apellido distinto en el nombre.",
     "cambios": {"solicitud": {"nombre": "Laura Beatriz Hernandes Castillo"}}, "errores": ["nombre"]},
    {"id": "08_documento_equivocado", "descripcion": "Se sube una solicitud como si fuera el plan de trabajo.",
     "titulo": {"plan_trabajo": "SOLICITUD DE SERVICIO SOCIAL"}, "errores": ["R005@plan_trabajo"]},
    {"id": "09_fecha_termino_anterior", "descripcion": "El plan tiene fecha de término anterior a la de inicio.",
     "cambios": {"plan_trabajo": {"fecha_fin": "2027-01-10"}}, "errores": ["fecha_fin"]},
    {"id": "10_escaneo_borroso", "descripcion": "La solicitud es un escaneo muy borroso e ilegible.",
     "rasterizar": {"solicitud": "borroso"}, "errores": ["R008@solicitud"], "estado": "REVISION_MANUAL",
     "requiere_ocr": False},
    {"id": "11_escaneo_correcto", "descripcion": "La solicitud es un escaneo limpio (requiere OCR) y todo es correcto.",
     "rasterizar": {"solicitud": "limpio"}, "errores": [], "estado": "SIN_OBSERVACIONES",
     "requiere_ocr": True},
    {"id": "12_faltan_firmas_plan", "descripcion": "El plan de trabajo no tiene ninguna de sus dos firmas.",
     "firmas": {"plan_trabajo": {"alumno": False, "responsable": False}},
     "errores": ["firma:alumno@plan_trabajo", "firma:responsable@plan_trabajo"]},
    {"id": "13_matricula_formato_invalido", "descripcion": "La matrícula de la solicitud tiene un carácter inválido.",
     "cambios": {"solicitud": {"matricula": "2153-01#7"}}, "errores": ["matricula"]},
    {"id": "14_institucion_distinta", "descripcion": "La solicitud nombra otra institución receptora.",
     "cambios": {"solicitud": {"institucion": "Secretaría de Educación de Quintana Roo"}},
     "errores": ["institucion"]},
    {"id": "15_pagina_sobrante", "descripcion": "La solicitud trae una tercera hoja en blanco.",
     "paginas_extra": {"solicitud": 2}, "errores": ["R007@solicitud"]},
    {"id": "16_varios_errores", "descripcion": "Fecha de inicio distinta y 400 horas en el plan, sin firma del alumno en la solicitud.",
     "cambios": {"plan_trabajo": {"fecha_inicio": "2027-02-08", "horas": 400}},
     "firmas": {"solicitud": {"alumno": False}},
     "errores": ["fecha_inicio", "horas", "firma:alumno@solicitud"]},
]


def generar_escenario(esc: dict[str, Any], carpeta: Path) -> dict[str, Any]:
    carpeta.mkdir(parents=True, exist_ok=True)
    datos_docs: dict[str, dict[str, Any]] = {t: copy.deepcopy(BASE) for t in ARCHIVOS}
    for tipo, cambios in esc.get("cambios", {}).items():
        datos_docs[tipo].update(cambios)

    escritos: dict[str, dict[str, Any]] = {}
    for tipo, archivo in ARCHIVOS.items():
        omitir = esc.get("omitir", {}).get(tipo, [])
        firmas = esc.get("firmas", {}).get(tipo, {})
        doc = dibujar_documento(
            tipo, datos_docs[tipo], firmas, campos_omitidos=omitir,
            paginas_extra=esc.get("paginas_extra", {}).get(tipo, 0),
            titulo=esc.get("titulo", {}).get(tipo),
        )
        modo = esc.get("rasterizar", {}).get(tipo)
        if modo:
            doc = _rasterizar(doc, dpi=200, borroso=(modo == "borroso"), ruido=(modo != "borroso"))
        doc.save(carpeta / archivo, garbage=3, deflate=True)
        doc.close()
        escritos[tipo] = {c: datos_docs[tipo][c] for c in CAMPOS_POR_DOC[tipo] if c not in omitir}

    verdad = {
        "escenario": esc["id"],
        "descripcion": esc["descripcion"],
        "documentos": ARCHIVOS,
        "errores_esperados": esc["errores"],
        "estado_esperado": esc.get("estado", "REQUIERE_CORRECCION"),
        "requiere_ocr": esc.get("requiere_ocr", False),
        "campos_escritos": escritos,
    }
    (carpeta / "ground_truth.json").write_text(json.dumps(verdad, ensure_ascii=False, indent=2), encoding="utf-8")
    return verdad


def main() -> None:
    # La consola de Windows usa cp1252 y no puede imprimir caracteres como «✓».
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Genera documentos sintéticos de prueba")
    ap.add_argument("--salida", default="samples", help="carpeta de salida (por defecto: samples)")
    args = ap.parse_args()
    salida = Path(args.salida)
    for esc in ESCENARIOS:
        generar_escenario(esc, salida / esc["id"])
        print(f"  ✓ {esc['id']}")
    print(f"\n{len(ESCENARIOS)} escenarios generados en {salida.resolve()}")


if __name__ == "__main__":
    main()
