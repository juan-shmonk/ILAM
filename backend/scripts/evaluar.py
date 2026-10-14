"""Evaluador: compara lo que detecta el sistema contra la respuesta correcta.

Recorre las carpetas de ``samples/`` (o la que indiques), ejecuta la
prevalidación sobre cada expediente y mide, contra ``ground_truth.json``:

  * precisión, recall y F1 de los errores detectados (sección 15 del plan),
  * falsos positivos (alertas de más) y falsos negativos (errores no vistos),
  * exactitud de extracción de campos, si el JSON incluye ``campos_escritos``.

Uso (desde backend/):
    python -m scripts.evaluar
    python -m scripts.evaluar --muestras otra_carpeta --json resultados.json

Cada error se identifica con una "clave":
    <campo>                      p. ej. "fecha_inicio", "horas", "matricula"
    firma:<id>@<documento>       p. ej. "firma:responsable@carta_aceptacion"
    R005@<doc> / R007@<doc> / R008@<doc>   formato, páginas o legibilidad
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from app.services import catalogo
from app.services.analysis import ocr
from app.services.analysis import textutil as tu
from app.services.offline import prevalidar_archivos


def claves_detectadas(reporte: dict[str, Any]) -> set[str]:
    """Convierte los hallazgos ERROR/ADVERTENCIA del reporte en claves comparables."""
    claves: set[str] = set()
    todos = [h for d in reporte["documentos"] for h in d["hallazgos"]] + reporte["cruzados"]
    for h in todos:
        if h["severidad"] not in ("ERROR", "ADVERTENCIA"):
            continue
        if h["regla"] == "R006":
            claves.add(f"firma:{h['campo']}@{h['documento']}")
        elif h["regla"] in ("R005", "R007", "R008"):
            claves.add(f"{h['regla']}@{h['documento']}")
        elif h["campo"]:
            claves.add(h["campo"])
        else:
            claves.add(f"{h['regla']}@{h['documento']}")
    return claves


def _igual(tipo: str, esperado: Any, dato: dict[str, Any] | None) -> bool:
    if not dato or dato.get("crudo") in (None, "", []):
        return False
    obtenido = dato.get("valor")
    if tipo == "fecha":
        return obtenido == esperado
    if tipo == "entero":
        return obtenido == esperado
    if tipo == "matricula":
        return tu.normalizar_matricula(str(obtenido)) == tu.normalizar_matricula(str(esperado))
    if tipo == "nombre":
        return tu.normalizar_nombre(str(obtenido)) == tu.normalizar_nombre(str(esperado))
    if tipo == "lista":
        return [tu.normalizar_texto(x) for x in obtenido or []] == [tu.normalizar_texto(x) for x in esperado]
    return tu.normalizar_texto(str(obtenido)) == tu.normalizar_texto(str(esperado))


def evaluar_carpeta(carpeta: Path) -> dict[str, Any]:
    verdad = json.loads((carpeta / "ground_truth.json").read_text(encoding="utf-8"))
    if verdad.get("requiere_ocr") and not ocr.ocr_disponible():
        return {"escenario": verdad["escenario"], "omitido": "requiere OCR (Tesseract no instalado)"}

    archivos = {tipo: carpeta / nombre for tipo, nombre in verdad["documentos"].items()}
    reporte = prevalidar_archivos(archivos)

    esperadas = set(verdad["errores_esperados"])
    detectadas = claves_detectadas(reporte)
    tp, fp, fn = esperadas & detectadas, detectadas - esperadas, esperadas - detectadas

    # Exactitud de extracción (solo en documentos que se pudieron leer)
    ok_campos = total_campos = 0
    fallos_campos: list[str] = []
    for doc in reporte["documentos"]:
        escritos = verdad.get("campos_escritos", {}).get(doc["tipo"], {})
        if not doc["calidad"]["legible"] or not doc["campos"] or not doc.get("archivo"):
            continue
        cfg = catalogo.tipo(doc["tipo"])
        resultado_campos = _campos_completos(carpeta / doc["archivo"], doc["tipo"])
        for campo, esperado in escritos.items():
            spec = cfg["campos"].get(campo)
            if not spec:
                continue
            total_campos += 1
            if _igual(spec["tipo"], esperado, resultado_campos.get(campo)):
                ok_campos += 1
            else:
                fallos_campos.append(f"{doc['tipo']}.{campo}")

    return {
        "escenario": verdad["escenario"],
        "descripcion": verdad["descripcion"],
        "esperadas": sorted(esperadas), "detectadas": sorted(detectadas),
        "tp": sorted(tp), "fp": sorted(fp), "fn": sorted(fn),
        "estado_esperado": verdad["estado_esperado"], "estado_obtenido": reporte["estado"],
        "estado_ok": verdad["estado_esperado"] == reporte["estado"],
        "campos_ok": ok_campos, "campos_total": total_campos, "campos_fallidos": fallos_campos,
    }


def _campos_completos(ruta: Path, tipo: str) -> dict[str, Any]:
    """Vuelve a analizar un archivo y devuelve sus campos crudos (para medir extracción)."""
    from app.services.analysis.pipeline import analizar_documento
    from app.services.storage import detectar_mime_archivo

    return analizar_documento(ruta, detectar_mime_archivo(ruta) or "", tipo).campos


def _prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def evaluar(muestras: Path) -> dict[str, Any]:
    resultados = [evaluar_carpeta(d) for d in sorted(muestras.iterdir()) if (d / "ground_truth.json").exists()]
    validos = [r for r in resultados if "omitido" not in r]
    tp = sum(len(r["tp"]) for r in validos)
    fp = sum(len(r["fp"]) for r in validos)
    fn = sum(len(r["fn"]) for r in validos)
    precision, recall, f1 = _prf(tp, fp, fn)
    campos_ok = sum(r["campos_ok"] for r in validos)
    campos_total = sum(r["campos_total"] for r in validos)
    return {
        "resultados": resultados,
        "resumen": {
            "expedientes": len(validos), "omitidos": len(resultados) - len(validos),
            "verdaderos_positivos": tp, "falsos_positivos": fp, "falsos_negativos": fn,
            "precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3),
            "estados_correctos": sum(r["estado_ok"] for r in validos),
            "exactitud_extraccion": round(campos_ok / campos_total, 3) if campos_total else None,
        },
    }


def main() -> None:
    # La consola de Windows usa cp1252 y no puede imprimir caracteres como «✓».
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Evalúa el sistema contra los documentos de muestra")
    ap.add_argument("--muestras", default="samples", help="carpeta con un subdirectorio por expediente")
    ap.add_argument("--json", help="guardar resultados detallados en este archivo")
    args = ap.parse_args()

    informe = evaluar(Path(args.muestras))
    for r in informe["resultados"]:
        if "omitido" in r:
            print(f"  -  {r['escenario']:<34} omitido: {r['omitido']}")
            continue
        marca = "✓" if not r["fp"] and not r["fn"] and r["estado_ok"] else "✗"
        extra = ""
        if r["fp"]:
            extra += f"  falsos positivos: {r['fp']}"
        if r["fn"]:
            extra += f"  NO detectado: {r['fn']}"
        if not r["estado_ok"]:
            extra += f"  estado {r['estado_obtenido']} (esperado {r['estado_esperado']})"
        if r["campos_fallidos"]:
            extra += f"  campos mal extraídos: {r['campos_fallidos']}"
        print(f"  {marca}  {r['escenario']:<34}{extra}")

    s = informe["resumen"]
    print("\nResumen")
    print(f"  Expedientes evaluados : {s['expedientes']} (omitidos: {s['omitidos']})")
    print(f"  Precisión / Recall / F1: {s['precision']:.2f} / {s['recall']:.2f} / {s['f1']:.2f}")
    print(f"  Falsos positivos / negativos: {s['falsos_positivos']} / {s['falsos_negativos']}")
    print(f"  Estado general correcto: {s['estados_correctos']} de {s['expedientes']}")
    if s["exactitud_extraccion"] is not None:
        print(f"  Exactitud de extracción de campos: {s['exactitud_extraccion']:.1%}")
    if args.json:
        Path(args.json).write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nDetalle guardado en {args.json}")


if __name__ == "__main__":
    main()
