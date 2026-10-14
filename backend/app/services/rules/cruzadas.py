"""Reglas que comparan datos ENTRE documentos del mismo expediente."""

from __future__ import annotations

from typing import Any

from rapidfuzz import fuzz

from app.services import catalogo
from app.services.analysis import textutil as tu
from app.services.rules.documento import etiqueta_campo
from app.services.rules.modelos import ADVERTENCIA, ERROR, INFO, OK, Hallazgo

# (regla, campo, modo de comparación)
#   exacto  -> los valores normalizados deben ser idénticos
#   nombre  -> similitud difusa con umbrales de nombres
#   texto   -> similitud difusa con umbrales de texto general
COMPARACIONES: list[tuple[str, str, str]] = [
    ("R015", "nombre", "nombre"),
    ("R002", "matricula", "exacto"),
    ("R016", "carrera", "texto"),
    ("R003", "fecha_inicio", "exacto"),
    ("R017", "fecha_fin", "exacto"),
    ("R018", "institucion", "texto"),
    ("R019", "horas", "exacto"),
    ("R020", "responsable", "nombre"),
]

_TITULOS_REGLA = {
    "R015": "Nombre consistente", "R002": "Matrícula consistente", "R016": "Carrera consistente",
    "R003": "Fecha de inicio consistente", "R017": "Fecha de término consistente",
    "R018": "Institución consistente", "R019": "Horas consistentes", "R020": "Responsable consistente",
}


def _mostrar(campo: str, dato: dict[str, Any]) -> str:
    if campo.startswith("fecha"):
        return tu.formatear_fecha(dato.get("valor"))
    return str(dato.get("valor"))


def _comparar(modo: str, a: Any, b: Any, umbrales: dict[str, Any]) -> tuple[str, float]:
    """Devuelve (nivel, similitud) con nivel en {'ok','advertencia','error'}.

    Con texto digital cualquier diferencia real es relevante, por eso solo una
    coincidencia total (tras normalizar acentos, mayúsculas y orden) es "ok".
    Una diferencia pequeña (typo, un apellido de menos, un error de OCR) es
    advertencia; una diferencia grande es error.
    """
    if modo == "exacto":
        return ("ok", 100.0) if a == b else ("error", 0.0)
    sim = float(fuzz.token_sort_ratio(str(a), str(b)))
    if sim >= 100:
        return "ok", sim
    minimo = umbrales["nombre_advertencia"] if modo == "nombre" else umbrales["texto_advertencia"]
    return ("advertencia", sim) if sim >= minimo else ("error", sim)


def evaluar_expediente(docs: dict[str, dict[str, Any]]) -> list[Hallazgo]:
    """Compara los documentos entre sí.

    ``docs`` es ``{tipo: resultado_del_analisis}`` con los documentos activos.
    Los documentos ilegibles o de formato equivocado no participan en la
    comparación (para no generar falsos errores).
    """
    req = catalogo.requisitos()
    tipos = catalogo.tipos_documento()
    orden = list(tipos.keys())
    hallazgos: list[Hallazgo] = []

    # --- R014: completitud del expediente ---
    presentes = [t for t in orden if t in docs]
    faltantes = [t for t in req["documentos_obligatorios"] if t not in docs]
    if faltantes:
        nombres = ", ".join(f"«{tipos[t]['nombre']}»" for t in faltantes)
        hallazgos.append(Hallazgo(
            "R014", INFO, "Expediente incompleto",
            f"Todavía no se cargan: {nombres}. Algunas comparaciones entre documentos no se pueden hacer aún.",
            accion="Carga los documentos faltantes para una prevalidación completa.", documentos=faltantes,
        ))
    else:
        hallazgos.append(Hallazgo("R014", OK, "Expediente completo",
                                  "Están cargados todos los documentos obligatorios del MVP."))

    # --- Documentos excluidos de la comparación ---
    utilizables: dict[str, dict[str, Any]] = {}
    for t in presentes:
        r = docs[t]
        if r["calidad"]["legible"] and r["formato"]["coincide"]:
            utilizables[t] = r
        else:
            hallazgos.append(Hallazgo(
                "R014", INFO, "Documento excluido de la comparación",
                f"«{tipos[t]['nombre']}» no se incluyó en las comparaciones porque no se pudo leer o no "
                "corresponde al formato esperado.", documento=t,
            ))

    # --- Comparaciones campo por campo ---
    for regla, campo, modo in COMPARACIONES:
        con_dato = {
            t: r["campos"][campo] for t, r in utilizables.items()
            if r["campos"].get(campo, {}).get("crudo") not in (None, "", []) and r["campos"][campo].get("valido")
        }
        if len(con_dato) < 2:
            continue
        base_tipo = req["fuente_base"].get(campo)
        if base_tipo not in con_dato:  # el documento base no está: usar el primero disponible
            base_tipo = next(t for t in orden if t in con_dato)
        base = con_dato[base_tipo]
        etiqueta = etiqueta_campo(campo)
        titulo = _TITULOS_REGLA[regla]
        incidencias: list[Hallazgo] = []

        for t, dato in con_dato.items():
            if t == base_tipo:
                continue
            nivel, sim = _comparar(modo, base["normalizado"], dato["normalizado"], req["umbrales"])
            if nivel == "ok":
                continue
            nb, nt = tipos[base_tipo]["nombre"], tipos[t]["nombre"]
            vb, vt = _mostrar(campo, base), _mostrar(campo, dato)
            if nivel == "advertencia":
                incidencias.append(Hallazgo(
                    regla, ADVERTENCIA, f"Posible diferencia en {etiqueta}",
                    f"El campo «{etiqueta}» se escribe distinto: «{nb}» dice «{vb}» y «{nt}» dice «{vt}» "
                    f"(similitud {sim:.0f}%).",
                    accion="Revisa que ambos documentos escriban el dato exactamente igual.",
                    documento=t, documentos=[base_tipo, t], campo=campo, pagina=dato.get("pagina"),
                    encontrado=vt, esperado=vb,
                ))
            else:
                incidencias.append(Hallazgo(
                    regla, ERROR, f"Inconsistencia en {etiqueta}",
                    f"El campo «{etiqueta}» no coincide: «{nb}» indica {vb}, pero «{nt}» indica {vt}.",
                    accion="Verifica cuál es el dato oficial y corrige el documento equivocado antes de "
                           "imprimirlo o de recabar firmas.",
                    documento=t, documentos=[base_tipo, t], campo=campo, pagina=dato.get("pagina"),
                    encontrado=vt, esperado=vb,
                ))
        if incidencias:
            hallazgos.extend(incidencias)
        else:
            nombres = " y ".join(tipos[t]["nombre"] for t in con_dato)
            hallazgos.append(Hallazgo(
                regla, OK, titulo, f"El campo «{etiqueta}» coincide entre: {nombres}.",
                documentos=list(con_dato.keys()), campo=campo,
            ))
    return hallazgos
