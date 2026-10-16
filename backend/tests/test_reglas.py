"""Prueba cada escenario sintético: los errores inyectados deben detectarse, y nada más."""

import json

import pytest

from app.services.analysis import ocr
from app.services.offline import prevalidar_archivos
from scripts.evaluar import claves_detectadas, evaluar
from scripts.generar_muestras import ESCENARIOS


@pytest.mark.parametrize("esc", ESCENARIOS, ids=[e["id"] for e in ESCENARIOS])
def test_escenario(muestras, esc):
    if esc.get("requiere_ocr") and not ocr.ocr_disponible():
        pytest.skip("Tesseract no está instalado")
    carpeta = muestras / esc["id"]
    verdad = json.loads((carpeta / "ground_truth.json").read_text(encoding="utf-8"))
    reporte = prevalidar_archivos({t: carpeta / f for t, f in verdad["documentos"].items()})

    assert claves_detectadas(reporte) == set(esc["errores"])
    assert reporte["estado"] == verdad["estado_esperado"]


def test_metricas_globales(muestras):
    resumen = evaluar(muestras)["resumen"]
    assert resumen["precision"] == 1.0
    assert resumen["recall"] == 1.0
    assert resumen["exactitud_extraccion"] == 1.0


def test_expediente_incompleto_no_es_error(muestras):
    """Con solo un documento, faltan comparaciones pero no debe marcarse como error."""
    carpeta = muestras / "01_correcto"
    reporte = prevalidar_archivos({"solicitud": carpeta / "solicitud.pdf"})
    assert reporte["estado"] == "SIN_OBSERVACIONES"
    assert set(reporte["completitud"]["faltantes"]) == {"plan_trabajo"}


def test_json_canonico_del_expediente(muestras):
    carpeta = muestras / "01_correcto"
    reporte = prevalidar_archivos({t: carpeta / f for t, f in
                                   {"solicitud": "solicitud.pdf", "plan_trabajo": "plan_trabajo.pdf"}.items()})
    exp = reporte["expediente_json"]["expediente"]
    assert exp["alumno"]["matricula"] == "21530177"
    assert exp["servicio"]["fecha_inicio"] == "2027-02-15"
    assert exp["servicio"]["horas"] == 480
    assert len(exp["plan"]["actividades"]) == 4


def test_hallazgo_explica_que_donde_y_que_hacer(muestras):
    carpeta = muestras / "02_fecha_inicio_distinta"
    reporte = prevalidar_archivos({t: carpeta / f for t, f in
                                   {"solicitud": "solicitud.pdf", "plan_trabajo": "plan_trabajo.pdf"}.items()})
    h = next(h for h in reporte["cruzados"] if h["severidad"] == "ERROR")
    assert h["regla"] == "R003" and h["campo"] == "fecha_inicio"
    assert "10/02/2027" in h["mensaje"] and "15/02/2027" in h["mensaje"]
    assert h["accion"]
