"""Construcción del reporte de prevalidación de un expediente.

El texto explicativo se genera con plantillas (determinista). Aquí es donde,
en una fase posterior, se podría conectar un LLM que reescriba los hallazgos
en lenguaje más natural, sin cambiar los hallazgos en sí.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.services import catalogo
from app.services.analysis import textutil as tu
from app.services.rules import cruzadas, documento
from app.services.rules.documento import etiqueta_campo
from app.services.rules.modelos import (
    ADVERTENCIA, ERROR, INFO, OK, REQUIERE_CORRECCION, REVISION_MANUAL, SIN_DOCUMENTOS,
    SIN_OBSERVACIONES, estado_de,
)

VERSION_MOTOR = "0.1.0"

AVISO = (
    "Esta prevalidación es una ayuda para detectar posibles errores antes de entregar tus documentos. "
    "No sustituye la revisión ni la aprobación oficial de la institución."
)

# Campos que se muestran en la tabla comparativa, en este orden.
CAMPOS_COMPARACION = ["nombre", "matricula", "carrera", "institucion", "responsable", "fecha_inicio", "fecha_fin", "horas"]


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def contar(hallazgos: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "errores": sum(h["severidad"] == ERROR for h in hallazgos),
        "advertencias": sum(h["severidad"] == ADVERTENCIA for h in hallazgos),
        "correctos": sum(h["severidad"] == OK for h in hallazgos),
        "info": sum(h["severidad"] == INFO for h in hallazgos),
    }


def redactar(estado: str, conteos: dict[str, int]) -> tuple[str, str]:
    """Devuelve (resumen, siguiente_paso) a partir del estado y los conteos."""
    if estado == SIN_DOCUMENTOS:
        return ("Todavía no hay documentos cargados.", "Sube tu primer documento para iniciar la prevalidación.")
    if estado == SIN_OBSERVACIONES:
        return (
            "La prevalidación no encontró observaciones en los documentos cargados.",
            "Puedes llevar tus documentos a revisión oficial. Recuerda que esta prevalidación no la sustituye.",
        )
    if estado == REVISION_MANUAL:
        return (
            "No se pudo leer con confiabilidad al menos uno de los documentos, por lo que no se pudo validar.",
            "Sube una versión más legible (PDF con texto digital, o una foto recta, nítida y bien iluminada).",
        )
    partes = []
    if conteos["errores"]:
        partes.append(_plural(conteos["errores"], "error", "errores"))
    if conteos["advertencias"]:
        partes.append(_plural(conteos["advertencias"], "advertencia", "advertencias"))
    return (
        f"Se detectaron {' y '.join(partes)}.",
        "Corrige las observaciones antes de imprimir el documento o de solicitar nuevas firmas, y vuelve a "
        "subirlo para comprobar.",
    )


def _valor_mostrar(campo: str, dato: dict[str, Any] | None) -> Any:
    if not dato or dato.get("crudo") in (None, "", []):
        return None
    if campo.startswith("fecha"):
        return tu.formatear_fecha(dato.get("valor")) if dato.get("valido") else dato.get("crudo")
    return dato.get("valor") if dato.get("valor") not in (None, "") else dato.get("crudo")


def construir_expediente_json(expediente_id: int, tramite: str, docs: list[dict[str, Any]]) -> dict[str, Any]:
    """Estructura canónica del expediente (sección 8 del plan), ya normalizada."""
    fuente = catalogo.requisitos()["fuente_base"]
    por_tipo = {d["tipo"]: d["resultado"] for d in docs}

    def canon(campo: str) -> Any:
        candidatos = [fuente.get(campo)] + [t for t in catalogo.ORDEN_TIPOS if t != fuente.get(campo)]
        for t in candidatos:
            dato = (por_tipo.get(t) or {}).get("campos", {}).get(campo)
            if dato and dato.get("valido") and dato.get("crudo") not in (None, "", []):
                return dato.get("valor")
        return None

    return {
        "expediente": {
            "id": expediente_id,
            "tramite": tramite,
            "alumno": {"nombre": canon("nombre"), "matricula": canon("matricula"), "carrera": canon("carrera")},
            "servicio": {
                "institucion": canon("institucion"),
                "responsable": canon("responsable"),
                "fecha_inicio": canon("fecha_inicio"),
                "fecha_fin": canon("fecha_fin"),
                "horas": canon("horas"),
            },
            "plan": {"actividades": canon("actividades") or []},
            "documentos": {
                d["tipo"]: {
                    "version": d.get("version"),
                    "campos": {k: c.get("valor") for k, c in d["resultado"]["campos"].items()
                               if c.get("crudo") not in (None, "", [])},
                }
                for d in docs
            },
        }
    }


def construir_reporte(expediente_id: int, tramite: str, docs: list[dict[str, Any]]) -> dict[str, Any]:
    """Genera el reporte completo.

    ``docs``: lista de documentos ACTIVOS del expediente, cada uno como
    ``{"id", "tipo", "version", "nombre_original", "resultado"}``.
    """
    tipos = catalogo.tipos_documento()
    orden = list(tipos.keys())
    docs = sorted(docs, key=lambda d: orden.index(d["tipo"]) if d["tipo"] in orden else 99)

    cruzados = [h.to_dict() for h in cruzadas.evaluar_expediente({d["tipo"]: d["resultado"] for d in docs})]

    secciones: list[dict[str, Any]] = []
    todos: list[dict[str, Any]] = []
    for d in docs:
        hall = [h.to_dict() for h in documento.evaluar_documento(d["tipo"], d["resultado"])]
        todos.extend(hall)
        # El estado de cada documento también considera las inconsistencias donde participa
        # (por ejemplo, la carta de aceptación es la referencia de las fechas).
        involucrado = [h for h in cruzados if d["tipo"] in h["documentos"] or h["documento"] == d["tipo"]]
        secciones.append({
            "documento_id": d["id"],
            "tipo": d["tipo"],
            "nombre": tipos[d["tipo"]]["nombre"],
            "version": d.get("version"),
            "archivo": d.get("nombre_original"),
            "estado": estado_de(hall + involucrado),
            "calidad": d["resultado"]["calidad"],
            "firmas": d["resultado"]["firmas"],
            "campos": {k: _valor_mostrar(k, c) for k, c in d["resultado"]["campos"].items()},
            "hallazgos": hall,
        })
    todos.extend(cruzados)

    estado = estado_de(todos) if docs else SIN_DOCUMENTOS
    conteos = contar(todos)
    resumen, siguiente = redactar(estado, conteos)

    # Tabla comparativa entre documentos
    conflictos = {h["campo"] for h in cruzados if h["severidad"] in (ERROR, ADVERTENCIA) and h["campo"]}
    comparacion = []
    for campo in CAMPOS_COMPARACION:
        valores = {d["tipo"]: _valor_mostrar(campo, d["resultado"]["campos"].get(campo)) for d in docs}
        if not any(v is not None for v in valores.values()):
            continue
        comparacion.append({
            "campo": campo,
            "etiqueta": etiqueta_campo(campo).capitalize(),
            "valores": valores,
            "consistente": campo not in conflictos,
        })

    presentes = [d["tipo"] for d in docs]
    return {
        "estado": estado,
        "resumen": resumen,
        "siguiente_paso": siguiente,
        "conteos": conteos,
        "completitud": {
            "presentes": presentes,
            "faltantes": [t for t in catalogo.requisitos()["documentos_obligatorios"] if t not in presentes],
        },
        "documentos": secciones,
        "cruzados": cruzados,
        "comparacion": comparacion,
        "expediente_json": construir_expediente_json(expediente_id, tramite, docs),
        "aviso": AVISO,
        "version_motor": VERSION_MOTOR,
        "version_requisitos": catalogo.requisitos()["version"],
        "generado_en": datetime.now(timezone.utc).isoformat(),
    }
