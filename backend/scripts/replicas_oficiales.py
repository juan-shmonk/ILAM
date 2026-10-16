"""Réplicas SINTÉTICAS de los formatos oficiales ITC-VI-PO-002-02 (solicitud) e -07 (plan).

Dibujan el formato con la misma estructura que el original (marcas "(n)",
líneas de guiones bajos, tabla de firmas) y lo llenan con datos inventados.
Cada valor puede escribirse como texto o pegarse como IMAGEN, que es lo que
pasa en la práctica cuando el alumno llena el formato en Google Docs. Sirven
para las pruebas automáticas sin usar documentos reales de alumnos.

Uso (desde backend/):
    python -m scripts.replicas_oficiales --salida replicas
    python -m scripts.replicas_oficiales --salida replicas --imagenes carrera,institucion,fecha_inicio
"""

from __future__ import annotations

import argparse
import io
import math
from pathlib import Path
from typing import Any

import pymupdf as fitz
from PIL import Image, ImageDraw, ImageFont

from app.services.analysis import textutil as tu

FUENTE = "helv"
TAM = 11
AVISO = "REPLICA DE PRUEBA - DATOS INVENTADOS"

DATOS: dict[str, Any] = {
    "nombre": "Ana Sofía Pech Canul",
    "apellido_paterno": "Pech", "apellido_materno": "Canul", "nombres": "Ana Sofía",
    "matricula": "21530412",
    "carrera": "Ingeniería en Sistemas Computacionales",
    "periodo_escolar": "Agosto/Diciembre 2026",
    "institucion": "Instituto Tecnológico de Cancún",
    "titular": "Mtra. Rosa Elena Chí Poot",
    "puesto_titular": "Directora",
    "programa": "Soporte Técnico",
    "modalidad": "Interno",
    "fecha_inicio": "2026-07-15",
    "fecha_fin": "2027-01-15",
    "actividades": "Mantenimiento preventivo y correctivo de equipos de cómputo, apoyo en la red del campus "
                   "y atención a usuarios en los laboratorios.",
    "tipo_programa": ["Otros"],
    "responsable": "Ing. Luis Alberto May Uc",
    "cargo_responsable": "Jefe del centro de cómputo",
}

OPCIONES_PROGRAMA = [
    ["Educación para adultos", "Desarrollo de comunidad", "Actividades deportivas"],
    ["Actividades cívicas", "Actividades culturales", "Medio ambiente"],
    ["Desarrollo sustentable", "Apoyo a la salud", "Otros"],
]


def _fuente_imagen(tam: int) -> ImageFont.ImageFont:
    for nombre in ("DejaVuSerif.ttf", "times.ttf", "Times New Roman.ttf", "LiberationSerif-Regular.ttf"):
        try:
            return ImageFont.truetype(nombre, tam)
        except OSError:
            continue
    return ImageFont.load_default()


def _png_de_texto(texto: str) -> bytes:
    """Texto como imagen PNG con transparencia (96 dpi aprox., como lo pega Google Docs)."""
    fuente = _fuente_imagen(17)
    caja = fuente.getbbox(texto)
    img = Image.new("RGBA", (caja[2] + 6, 27), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((3, 2), texto, font=fuente, fill=(60, 60, 60, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class Linea:
    """Escribe una línea del formato de izquierda a derecha."""

    def __init__(self, pagina: fitz.Page, x: float, y: float, imagenes: set[str]):
        self.p, self.x, self.y, self.imagenes = pagina, x, y, imagenes

    def texto(self, t: str, negrita: bool = False) -> "Linea":
        fuente = "hebo" if negrita else FUENTE
        self.p.insert_text((self.x, self.y), t, fontname=fuente, fontsize=TAM)
        self.x += fitz.get_text_length(t, fontname=fuente, fontsize=TAM)
        return self

    def campo(self, clave: str, valor: str | None, ancho: float) -> "Linea":
        """Espacio de ``ancho`` puntos con el valor como texto (sobre guiones) o como imagen."""
        guion = fitz.get_text_length("_", fontname=FUENTE, fontsize=TAM)
        valor = valor or ""
        if valor and clave in self.imagenes:
            self.p.insert_text((self.x, self.y), "_" * int(ancho / guion), fontname=FUENTE, fontsize=TAM)
            png = _png_de_texto(valor)
            w = Image.open(io.BytesIO(png)).width * 0.75
            self.p.insert_image(fitz.Rect(self.x + 2, self.y - 15, self.x + 2 + w, self.y + 5), stream=png)
        else:
            usado = fitz.get_text_length(valor, fontname=FUENTE, fontsize=TAM)
            relleno = "_" * max(int((ancho - usado) / guion), 2)
            self.p.insert_text((self.x, self.y), "__" + valor + relleno, fontname=FUENTE, fontsize=TAM)
        self.x += ancho + 3
        return self


def _fecha(iso: str | None) -> tuple[str, str, str]:
    if not iso:
        return "", "", ""
    d = tu.date.fromisoformat(iso)
    return str(d.day), tu.MESES_NOMBRE[d.month], str(d.year)


def _encabezado(p: fitz.Page, titulo_tabla: str) -> None:
    p.draw_rect(fitz.Rect(57, 50, 555, 120), width=1.2)
    p.draw_line((150, 50), (150, 120))
    p.draw_line((380, 50), (380, 120))
    p.insert_text((160, 90), titulo_tabla, fontname="hebo", fontsize=TAM)
    p.insert_text((386, 66), "Fecha de aprobación: 17 febrero 2023", fontname="hebo", fontsize=8)
    p.insert_text((386, 90), "Revisión: 0", fontname="hebo", fontsize=TAM)
    p.insert_text((386, 112), "Página 1 de 1", fontname="hebo", fontsize=TAM)
    p.insert_text((180, 780), AVISO, fontname=FUENTE, fontsize=7)


def _garabato(p: fitz.Page, x0: float, y0: float, x1: float, y1: float) -> None:
    """Simula una firma o un sello a mano."""
    puntos = []
    for i in range(60):
        t = i / 59
        puntos.append((x0 + (x1 - x0) * t, (y0 + y1) / 2 + (y1 - y0) * 0.35 * math.sin(t * 14) * (1 - 0.5 * t)))
    p.draw_polyline(puntos, color=(0.1, 0.1, 0.4), width=1.4)


def generar_solicitud(ruta: Path, datos: dict[str, Any] | None = None, imagenes: set[str] | None = None) -> Path:
    d = DATOS | (datos or {})
    im = imagenes or set()
    doc = fitz.open()
    p = doc.new_page(width=612, height=792)
    _encabezado(p, "Formato para Solicitud de Servicio Social")
    p.insert_text((130, 160), "DEPARTAMENTO DE GESTIÓN TECNOLÓGICA Y VINCULACIÓN", fontname="hebo", fontsize=TAM)
    p.insert_text((210, 174), "SOLICITUD DE SERVICIO SOCIAL", fontname="hebo", fontsize=TAM)
    p.insert_text((57, 202), "DATOS PERSONALES", fontname="hebo", fontsize=TAM)
    Linea(p, 59, 214, im).texto("Nombre completo (1) ").campo("nombre", d["nombre"], 390)
    (Linea(p, 57, 237, im).texto("Sexo (2) ").campo("sexo", "M", 30).texto("Teléfono: (3) ")
     .campo("telefono", "9980000000", 90).texto("Domicilio: (4) ").campo("domicilio", "Calle Inventada 1", 120))
    p.insert_text((57, 260), "ESCOLARIDAD", fontname="hebo", fontsize=TAM)
    (Linea(p, 57, 272, im).texto("No. de Control: (5) ").campo("matricula", d["matricula"], 70)
     .texto("Carrera: (6) ").campo("carrera", d["carrera"], 270))
    (Linea(p, 57, 295, im).texto("Periodo: (7) ").campo("periodo_escolar", d["periodo_escolar"], 370)
     .texto("Semestre: (8)"))
    p.insert_text((57, 306), "_____9_____", fontname=FUENTE, fontsize=TAM)
    p.insert_text((57, 329), "DATOS DEL PROGRAMA", fontname="hebo", fontsize=TAM)
    Linea(p, 57, 341, im).texto("Dependencia Oficial: (9) ").campo("institucion", d["institucion"], 360)
    Linea(p, 57, 364, im).texto("Titular de la Dependencia: (10) ").campo("titular", d["titular"], 330)
    Linea(p, 57, 387, im).texto("Puesto: (11) ").campo("puesto_titular", d["puesto_titular"], 410)
    Linea(p, 57, 410, im).texto("Nombre del Programa: (12) ").campo("programa", d["programa"], 350)
    ini, fin = _fecha(d["fecha_inicio"]), _fecha(d["fecha_fin"])
    (Linea(p, 57, 433, im).texto("Modalidad: (13) ").campo("modalidad", d["modalidad"], 60)
     .texto("Fecha de Inicio: (14) ").campo("fecha_inicio", "/".join(ini) if ini[0] else "", 75)
     .texto("Fecha de Terminación: (15) ").campo("fecha_fin", "/".join(fin) if fin[0] else "", 75))
    p.insert_text((57, 456), "Actividades: (16)", fontname=FUENTE, fontsize=TAM)
    if d["actividades"]:
        p.insert_textbox(fitz.Rect(57, 460, 555, 500), d["actividades"], fontname=FUENTE, fontsize=TAM)
    p.insert_text((57, 513), "Tipo de programa: (17)", fontname="hebo", fontsize=TAM)
    for fila, opciones in enumerate(OPCIONES_PROGRAMA):
        for col, opcion in enumerate(opciones):
            marca = "(x)" if opcion in d["tipo_programa"] else "( )"
            p.insert_text((57 + col * 165, 536 + fila * 20), f"{marca} {opcion}", fontname=FUENTE, fontsize=TAM)
    p.insert_text((57, 610), "PARA USO EXCLUSIVO DE LA OFICINA DE SERVICIO SOCIAL", fontname=FUENTE, fontsize=TAM)
    p.insert_text((57, 635), "ACEPTADO: (18) SI (   ); NO (   ) MOTIVO: (19) " + "_" * 40, fontname=FUENTE, fontsize=TAM)
    p.insert_text((57, 660), "OBSERVACIONES: (20)", fontname=FUENTE, fontsize=TAM)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    doc.save(ruta)
    doc.close()
    return ruta


def generar_plan(ruta: Path, datos: dict[str, Any] | None = None, imagenes: set[str] | None = None,
                 firmas: set[str] | None = None) -> Path:
    """``firmas``: subconjunto de {"responsable", "sello", "alumno"} que se dibujan."""
    d = DATOS | (datos or {})
    im = imagenes or set()
    firmas = firmas or set()
    doc = fitz.open()
    p = doc.new_page(width=612, height=792)
    _encabezado(p, "Plan de trabajo del (la) prestante.")
    p.insert_text((130, 150), "DEPARTAMENTO DE GESTIÓN TECNOLÓGICA Y VINCULACIÓN", fontname="hebo", fontsize=TAM)
    p.insert_text((220, 164), "OFICINA DE SERVICIO SOCIAL", fontname="hebo", fontsize=TAM)
    p.insert_text((260, 190), "PLAN DE TRABAJO", fontname="hebo", fontsize=TAM)
    (Linea(p, 65, 231, im).texto("Nombre: (1) ").campo("apellido_paterno", d["apellido_paterno"], 130)
     .campo("apellido_materno", d["apellido_materno"], 130).campo("nombres", d["nombres"], 140))
    p.insert_text((170, 243), "Apellido Paterno", fontname=FUENTE, fontsize=TAM)
    p.insert_text((300, 243), "Apellido Materno", fontname=FUENTE, fontsize=TAM)
    p.insert_text((450, 243), "Nombre (s)", fontname=FUENTE, fontsize=TAM)
    (Linea(p, 65, 266, im).texto("Carrera: (2) ").campo("carrera", d["carrera"], 240)
     .texto("No de Control (3) ").campo("matricula", d["matricula"], 80))
    p.insert_text((65, 280), "Periodo Reportado:", fontname="hebo", fontsize=TAM)
    (ini_d, ini_m, ini_a), (fin_d, fin_m, fin_a) = _fecha(d["fecha_inicio"]), _fecha(d["fecha_fin"])
    (Linea(p, 65, 306, im).texto("Del día: (4) ").campo("fecha_inicio", ini_d, 25).texto("mes")
     .campo("fecha_inicio", ini_m, 60).texto("año ").campo("fecha_inicio", ini_a, 35).texto(";   al  día: ")
     .campo("fecha_fin", fin_d, 25).texto("mes ").campo("fecha_fin", fin_m, 60).texto("año ")
     .campo("fecha_fin", fin_a, 35))
    Linea(p, 65, 329, im).texto("Dependencia:(5) ").campo("institucion", d["institucion"], 390)
    Linea(p, 65, 352, im).texto("Programa:(6) ").campo("programa", d["programa"], 400)
    p.insert_text((65, 375), "Plan de trabajo: (7)", fontname=FUENTE, fontsize=TAM)
    if d["actividades"]:
        p.insert_textbox(fitz.Rect(65, 379, 555, 430), d["actividades"], fontname=FUENTE, fontsize=TAM)
    for i in range(6):
        p.insert_text((65, 440 + i * 17), "_" * 80, fontname=FUENTE, fontsize=TAM)

    # Tabla de firmas
    p.draw_rect(fitz.Rect(59, 550, 555, 705), width=1)
    p.draw_line((222, 550), (222, 705))
    p.draw_line((365, 550), (365, 705))
    p.draw_line((365, 608), (555, 608))
    p.insert_text((452, 582), "(10)", fontname=FUENTE, fontsize=TAM)
    p.insert_text((380, 594), "_" * 28, fontname=FUENTE, fontsize=TAM)
    p.insert_text((395, 605), "FIRMA DEL INTERESADO (A)", fontname=FUENTE, fontsize=TAM)
    p.insert_text((372, 650), "_" * 14 + "(11)" + "_" * 12, fontname=FUENTE, fontsize=TAM)
    p.insert_text((375, 662), "Vo. Bo. OFICINA SERVICIO SOCIAL", fontname=FUENTE, fontsize=TAM)
    p.insert_text((385, 674), "DEL INSTITUTO TECNOLÓGICO", fontname=FUENTE, fontsize=TAM)
    p.insert_text((65, 652), "(8)", fontname=FUENTE, fontsize=TAM)
    p.insert_text((70, 662), "_" * 25, fontname=FUENTE, fontsize=TAM)
    resp = d["responsable"] or ""
    if resp:
        p.insert_textbox(fitz.Rect(70, 664, 220, 690), resp, fontname=FUENTE, fontsize=TAM, align=1)
    if d["cargo_responsable"]:
        p.insert_text((75, 700), d["cargo_responsable"], fontname=FUENTE, fontsize=TAM)
    p.insert_text((288, 686), "(9)", fontname=FUENTE, fontsize=TAM)
    p.insert_text((280, 698), "SELLO", fontname=FUENTE, fontsize=TAM)
    if "responsable" in firmas:
        _garabato(p, 90, 610, 200, 650)
    if "sello" in firmas:
        p.draw_circle((294, 620), 35, color=(0.2, 0.2, 0.6), width=2)
        p.insert_text((268, 623), "DEPENDENCIA", fontname=FUENTE, fontsize=7, color=(0.2, 0.2, 0.6))
    if "alumno" in firmas:
        _garabato(p, 400, 560, 520, 592)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    doc.save(ruta)
    doc.close()
    return ruta


def rasterizar(origen: Path, destino: Path, dpi: int = 200) -> Path:
    """Convierte un PDF en un PDF de solo imagen (como un escaneo limpio)."""
    src = fitz.open(origen)
    out = fitz.open()
    for pagina in src:
        pix = pagina.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
        nueva = out.new_page(width=pagina.rect.width, height=pagina.rect.height)
        nueva.insert_image(nueva.rect, stream=pix.tobytes("png"))
    out.save(destino)
    return destino


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--salida", type=Path, default=Path("replicas"))
    ap.add_argument("--imagenes", default="", help="Campos a pegar como imagen, separados por comas")
    ap.add_argument("--firmado", action="store_true", help="Dibujar firmas y sello en el plan")
    args = ap.parse_args(argv)
    imagenes = {c.strip() for c in args.imagenes.split(",") if c.strip()}
    generar_solicitud(args.salida / "solicitud.pdf", imagenes=imagenes)
    generar_plan(args.salida / "plan_trabajo.pdf", imagenes=imagenes,
                 firmas={"responsable", "sello", "alumno"} if args.firmado else set())
    print(f"Réplicas creadas en {args.salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
