"""Formatos oficiales ITC-VI-PO-002-02 (solicitud) y -07 (plan), leídos por zonas.

Se usan réplicas SINTÉTICAS de los formatos (scripts/replicas_oficiales.py):
ningún documento real de alumnos entra al repositorio.
"""

from pathlib import Path

import pytest

from app.services.analysis import ocr
from app.services.analysis import textutil as tu
from app.services.analysis.pipeline import analizar_documento
from app.services.analysis.plantilla import Caja, PalabraLayout, partir_palabra
from app.services.offline import prevalidar_archivos
from scripts.evaluar import claves_detectadas
from scripts.replicas_oficiales import DATOS, generar_plan, generar_solicitud, rasterizar

requiere_ocr = pytest.mark.skipif(not ocr.ocr_disponible(), reason="Tesseract no está instalado")
TODAS_LAS_FIRMAS = {"responsable", "sello", "alumno"}
CAMPOS_IMAGEN = {"carrera", "institucion", "titular", "periodo_escolar", "fecha_inicio", "fecha_fin", "programa"}


def _expediente(tmp: Path, sol: dict | None = None, plan: dict | None = None, imagenes: set | None = None,
                firmas: set | None = None) -> dict:
    s = generar_solicitud(tmp / "solicitud.pdf", sol, imagenes)
    p = generar_plan(tmp / "plan_trabajo.pdf", plan, imagenes, firmas)
    return prevalidar_archivos({"solicitud": s, "plan_trabajo": p})


def _hallazgos(reporte: dict, regla: str) -> list[dict]:
    todos = [h for d in reporte["documentos"] for h in d["hallazgos"]] + reporte["cruzados"]
    return [h for h in todos if h["regla"] == regla]


def _campos(reporte: dict, tipo: str) -> dict:
    return next(d for d in reporte["documentos"] if d["tipo"] == tipo)["campos"]


# ---------------------------------------------------------------------------
# Piezas
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("texto,esperado", [
    ("22530305______Carrera:", ["22530305", "Carrera:"]),
    ("Dependencia:(5)", ["Dependencia:", "(5)"]),
    ("________________(11)_____________", ["(11)"]),
    ("___________Leon______Cupul____Juan", ["Leon", "Cupul", "Juan"]),
    ("(x)", ["(x)"]),
])
def test_partir_palabras_pegadas(texto, esperado):
    partes = partir_palabra(PalabraLayout(Caja(0, 0, 10 * len(texto), 10), texto))
    assert [p.texto for p in partes] == esperado
    assert all(a.caja.x1 <= b.caja.x0 for a, b in zip(partes, partes[1:]))  # cajas en orden y sin traslape


@pytest.mark.parametrize("texto,esperado", [
    ("15/julio/2026", (2026, 7, 15)),
    ("15 mes julio año 2026", (2026, 7, 15)),
    ("15 mes encro año 2027", (2027, 1, 15)),  # error típico del OCR
    ("1 Septiembre 2026", (2026, 9, 1)),
    ("mes año", None),
    ("15 mes año 2026", None),
])
def test_fecha_en_partes(texto, esperado):
    resultado = tu.parse_fecha(texto)
    assert (resultado.year, resultado.month, resultado.day) == esperado if esperado else resultado is None


# ---------------------------------------------------------------------------
# Extracción
# ---------------------------------------------------------------------------
def test_formato_oficial_texto_digital(tmp_path):
    reporte = _expediente(tmp_path)
    sol, plan = _campos(reporte, "solicitud"), _campos(reporte, "plan_trabajo")
    assert sol["nombre"] == DATOS["nombre"]
    assert sol["matricula"] == plan["matricula"] == DATOS["matricula"]
    assert sol["carrera"] == plan["carrera"] == DATOS["carrera"]
    assert sol["institucion"] == plan["institucion"] == DATOS["institucion"]
    assert sol["titular"] == DATOS["titular"]
    assert sol["fecha_inicio"] == plan["fecha_inicio"] == "15/07/2026"
    assert sol["fecha_fin"] == plan["fecha_fin"] == "15/01/2027"
    assert sol["tipo_programa"] == ["Otros"]
    assert tu.normalizar_nombre(plan["nombre"]).split() == ["pech", "canul", "ana", "sofia"]  # orden del plan
    assert plan["responsable"] == DATOS["responsable"]
    assert plan["cargo_responsable"] == DATOS["cargo_responsable"]
    for d in reporte["documentos"]:
        assert d["hallazgos"][0]["regla"] == "R008"
    # Sin firmar todavía: se avisa, pero no es una observación.
    pendientes = [h for h in _hallazgos(reporte, "R006") if h["severidad"] == "INFO"]
    assert len(pendientes) == 3
    assert reporte["estado"] == "SIN_OBSERVACIONES"


def test_se_elige_la_version_del_formato(tmp_path):
    ruta = generar_plan(tmp_path / "plan.pdf")
    resultado = analizar_documento(ruta, "application/pdf", "plan_trabajo").to_dict()
    assert resultado["formato"]["version"] == "ITC-VI-PO-002-07-rev0"
    assert resultado["formato"]["coincide"]


@requiere_ocr
def test_valores_pegados_como_imagen(tmp_path):
    """Lo que pasa al llenar el formato en Google Docs: el dato es una imagen sobre la línea."""
    reporte = _expediente(tmp_path, imagenes=CAMPOS_IMAGEN)
    sol, plan = _campos(reporte, "solicitud"), _campos(reporte, "plan_trabajo")
    for campo in ("carrera", "institucion", "programa"):
        assert tu.normalizar_texto(sol[campo]) == tu.normalizar_texto(DATOS[campo])
        assert tu.normalizar_texto(plan[campo]) == tu.normalizar_texto(DATOS[campo])
    assert tu.normalizar_nombre(sol["titular"]) == tu.normalizar_nombre(DATOS["titular"])
    assert sol["fecha_inicio"] == plan["fecha_inicio"] == "15/07/2026"
    assert sol["fecha_fin"] == plan["fecha_fin"] == "15/01/2027"
    assert reporte["estado"] == "SIN_OBSERVACIONES"


def test_sin_ocr_un_dato_en_imagen_no_es_error(tmp_path, monkeypatch):
    """Si no hay Tesseract, el campo en imagen se marca como no legible (advertencia), no como vacío."""
    monkeypatch.setattr(ocr, "ocr_disponible", lambda: False)
    reporte = _expediente(tmp_path, imagenes={"carrera"})
    r010 = [h for h in _hallazgos(reporte, "R010") if h["campo"] == "carrera"]
    assert r010 and all(h["severidad"] == "ADVERTENCIA" and h["titulo"] == "Campo no legible" for h in r010)


@requiere_ocr
def test_escaneo_del_formato(tmp_path):
    """Un escaneo (PDF de solo imagen) se lee con el OCR de la página y las mismas zonas."""
    ruta = rasterizar(generar_solicitud(tmp_path / "s.pdf"), tmp_path / "s_escaneo.pdf")
    campos = analizar_documento(ruta, "application/pdf", "solicitud").to_dict()["campos"]
    assert tu.normalizar_nombre(campos["nombre"]["valor"]) == tu.normalizar_nombre(DATOS["nombre"])
    assert campos["matricula"]["valor"] == DATOS["matricula"]
    assert tu.normalizar_texto(campos["carrera"]["valor"]) == tu.normalizar_texto(DATOS["carrera"])
    assert campos["fecha_fin"]["valor"] == DATOS["fecha_fin"]
    assert campos["tipo_programa"]["valor"] == ["Otros"]
    assert all(c["fuente"] == "ocr" for c in campos.values() if c["crudo"])


# ---------------------------------------------------------------------------
# Reglas sobre los formatos oficiales
# ---------------------------------------------------------------------------
def test_fecha_distinta_entre_solicitud_y_plan(tmp_path):
    reporte = _expediente(tmp_path, plan={"fecha_inicio": "2026-07-13"})  # sigue durando más de 6 meses
    assert claves_detectadas(reporte) == {"fecha_inicio"}
    h = next(h for h in _hallazgos(reporte, "R003") if h["severidad"] == "ERROR")
    assert "15/07/2026" in h["mensaje"] and "13/07/2026" in h["mensaje"]


def test_campo_obligatorio_vacio(tmp_path):
    reporte = _expediente(tmp_path, sol={"programa": ""})
    assert claves_detectadas(reporte) == {"programa"}
    assert reporte["estado"] == "REQUIERE_CORRECCION"


def test_matricula_distinta(tmp_path):
    reporte = _expediente(tmp_path, plan={"matricula": "21530421"})
    assert claves_detectadas(reporte) == {"matricula"}


def test_dos_tipos_de_programa_marcados(tmp_path):
    reporte = _expediente(tmp_path, sol={"tipo_programa": ["Otros", "Medio ambiente"]})
    assert claves_detectadas(reporte) == {"tipo_programa"}


def test_firmas_y_sello_detectados(tmp_path):
    reporte = _expediente(tmp_path, firmas=TODAS_LAS_FIRMAS)
    r006 = _hallazgos(reporte, "R006")
    assert {h["campo"] for h in r006 if h["severidad"] == "OK"} == TODAS_LAS_FIRMAS


def test_falta_solo_una_firma(tmp_path):
    reporte = _expediente(tmp_path, firmas={"responsable", "alumno"})
    r006 = {h["campo"]: h["severidad"] for h in _hallazgos(reporte, "R006")}
    assert r006 == {"responsable": "OK", "sello": "INFO", "alumno": "OK"}
