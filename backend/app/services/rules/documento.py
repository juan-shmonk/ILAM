"""Reglas que se aplican a UN documento (deterministas y explicables)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

from app.services import catalogo
from app.services.analysis import textutil as tu
from app.services.rules.modelos import ADVERTENCIA, ERROR, INFO, OK, Hallazgo


@dataclass
class ContextoDoc:
    tipo: str
    cfg: dict[str, Any]  # configuración del tipo de documento
    req: dict[str, Any]  # requisitos del trámite
    res: dict[str, Any]  # resultado del análisis (calidad, formato, campos, firmas)

    @property
    def nombre_doc(self) -> str:
        return self.cfg["nombre"]

    def campo(self, nombre: str) -> dict[str, Any]:
        return self.res["campos"].get(nombre) or {}

    def presente(self, nombre: str) -> bool:
        return self.campo(nombre).get("crudo") not in (None, "", [])

    def h(self, regla: str, sev: str, titulo: str, mensaje: str, **kw: Any) -> Hallazgo:
        return Hallazgo(regla=regla, severidad=sev, titulo=titulo, mensaje=mensaje, documento=self.tipo, **kw)


Regla = Callable[[ContextoDoc], list[Hallazgo]]

_ETIQUETAS_CAMPO = {
    "nombre": "nombre del alumno", "matricula": "matrícula", "carrera": "carrera",
    "institucion": "institución receptora", "responsable": "responsable",
    "cargo_responsable": "cargo del responsable", "fecha_inicio": "fecha de inicio",
    "fecha_fin": "fecha de término", "horas": "total de horas", "actividades": "actividades",
    "programa": "nombre del programa", "titular": "titular de la dependencia",
    "puesto_titular": "puesto del titular", "modalidad": "modalidad", "periodo_escolar": "periodo",
    "tipo_programa": "tipo de programa",
}


def etiqueta_campo(campo: str) -> str:
    return _ETIQUETAS_CAMPO.get(campo, campo)


# ----------------------------------------------------------------------------
# Compuertas: legibilidad (R008), formato esperado (R005) y páginas (R007)
# ----------------------------------------------------------------------------
def r008_legible(ctx: ContextoDoc) -> list[Hallazgo]:
    cal = ctx.res["calidad"]
    if cal["legible"]:
        if cal["metodo"] == "texto_digital" or cal["confianza_ocr"] is None:
            detalle = "PDF con texto digital"
        else:
            detalle = f"lectura por OCR, confianza {cal['confianza_ocr']:.0f}%"
        return [ctx.h("R008", OK, "Documento legible", f"El documento se pudo leer correctamente ({detalle}).")]
    motivo = cal.get("motivo") or "No se pudo leer el documento."
    return [ctx.h(
        "R008", ADVERTENCIA, "Documento no legible", motivo,
        accion="Sube un PDF con texto digital o una foto/escaneo más nítido, recto y bien iluminado.",
    )]


def r005_formato(ctx: ContextoDoc) -> list[Hallazgo]:
    fmt = ctx.res["formato"]
    if fmt["coincide"]:
        return [ctx.h("R005", OK, "Formato esperado", f"El documento corresponde a «{ctx.nombre_doc}».")]
    detectado = fmt.get("detectado")
    otro = catalogo.tipo(detectado) if detectado else None
    if otro:
        mensaje = f"Elegiste «{ctx.nombre_doc}», pero el archivo parece ser «{otro['nombre']}»."
        accion = "Sube este archivo en el tipo de documento correcto o carga el documento que corresponde."
    else:
        mensaje = f"No se encontró el encabezado propio de «{ctx.nombre_doc}» en el archivo."
        accion = "Verifica que subiste el documento correcto y que se ve completo, incluyendo el título."
    return [ctx.h("R005", ERROR, "Formato no coincide", mensaje, accion=accion,
                  encontrado=detectado, esperado=ctx.tipo)]


def r007_paginas(ctx: ContextoDoc) -> list[Hallazgo]:
    n = ctx.res["calidad"]["n_paginas"]
    rango = ctx.cfg.get("paginas")
    if not rango:
        return []
    if rango["min"] <= n <= rango["max"]:
        return [ctx.h("R007", OK, "Páginas completas", f"El documento tiene {n} página(s), dentro de lo esperado.")]
    esperado = f"{rango['min']}" if rango["min"] == rango["max"] else f"entre {rango['min']} y {rango['max']}"
    return [ctx.h(
        "R007", ERROR, "Páginas incompletas o de más",
        f"El documento tiene {n} página(s) y se esperaban {esperado}.",
        accion="Verifica que subiste todas las páginas del documento (y solo las de este documento).",
        encontrado=n, esperado=esperado,
    )]


# ----------------------------------------------------------------------------
# Reglas de contenido
# ----------------------------------------------------------------------------
def r001_nombre(ctx: ContextoDoc) -> list[Hallazgo]:
    if "nombre" not in ctx.cfg["campos"]:
        return []
    if ctx.presente("nombre"):
        return [ctx.h("R001", OK, "Nombre presente", f"Nombre del alumno: {ctx.campo('nombre')['valor']}.",
                      campo="nombre", pagina=ctx.campo("nombre").get("pagina"))]
    return [ctx.h("R001", ERROR, "Falta el nombre", "Falta el nombre del alumno.",
                  accion="Escribe el nombre completo del alumno en el espacio del nombre.",
                  campo="nombre")]


def r010_obligatorios(ctx: ContextoDoc) -> list[Hallazgo]:
    faltantes = [
        k for k, spec in ctx.cfg["campos"].items()
        if spec.get("obligatorio") and k != "nombre" and not ctx.presente(k)
    ]
    if not faltantes:
        return [ctx.h("R010", OK, "Campos obligatorios", "Todos los campos obligatorios están presentes.")]
    salida = []
    for k in faltantes:
        if ctx.campo(k).get("ilegible"):  # el dato parece estar, pero no se pudo leer: no es un error del alumno
            salida.append(ctx.h(
                "R010", ADVERTENCIA, "Campo no legible",
                f"No se pudo leer el campo «{etiqueta_campo(k)}» en {ctx.nombre_doc}: {ctx.campo(k).get('error')}.",
                accion="Revisa ese campo manualmente. Si lo llenaste pegando una imagen, escríbelo como texto.",
                campo=k, pagina=ctx.campo(k).get("pagina")))
        else:
            salida.append(ctx.h(
                "R010", ERROR, "Campo obligatorio vacío", f"Falta el campo «{etiqueta_campo(k)}» en {ctx.nombre_doc}.",
                accion=f"Completa el campo «{etiqueta_campo(k)}» antes de imprimir el documento.", campo=k))
    return salida


def r023_opcion_unica(ctx: ContextoDoc) -> list[Hallazgo]:
    """Listas de casillas ("Tipo de programa"): debe haber exactamente una marcada."""
    salida = []
    for k, spec in ctx.cfg["campos"].items():
        if spec["tipo"] != "opcion" or not ctx.presente(k):
            continue
        marcadas = ctx.campo(k)["valor"]
        if len(marcadas) == 1:
            salida.append(ctx.h("R023", OK, "Opción marcada", f"{etiqueta_campo(k).capitalize()}: {marcadas[0]}.",
                                campo=k))
        else:
            salida.append(ctx.h(
                "R023", ADVERTENCIA, "Más de una opción marcada",
                f"En «{etiqueta_campo(k)}» hay {len(marcadas)} opciones marcadas: {', '.join(marcadas)}.",
                accion="Marca solo una opción.", campo=k, encontrado=marcadas))
    return salida


def r011_matricula(ctx: ContextoDoc) -> list[Hallazgo]:
    if not ctx.presente("matricula"):
        return []  # ya lo reporta R010
    valor = ctx.campo("matricula")["valor"]
    if re.match(ctx.req["matricula_regex"], valor):
        return [ctx.h("R011", OK, "Matrícula válida", f"Matrícula: {valor}.", campo="matricula",
                      pagina=ctx.campo("matricula").get("pagina"))]
    return [ctx.h(
        "R011", ERROR, "Matrícula con formato inválido",
        f"La matrícula «{valor}» no tiene un formato válido.",
        accion="Revisa que la matrícula esté completa y sin caracteres extra.",
        campo="matricula", encontrado=valor, esperado=ctx.req["matricula_regex"],
    )]


def r012_fechas_validas(ctx: ContextoDoc) -> list[Hallazgo]:
    salida: list[Hallazgo] = []
    revisadas = 0
    for k, spec in ctx.cfg["campos"].items():
        if spec["tipo"] != "fecha" or not ctx.presente(k):
            continue
        revisadas += 1
        campo = ctx.campo(k)
        if not campo.get("valido") and campo.get("fuente") in ("ocr", "ocr_zona"):
            # Leída por OCR: puede ser un error de lectura y no del documento.
            salida.append(ctx.h(
                "R012", ADVERTENCIA, "Fecha no legible",
                f"No se pudo interpretar con certeza la {etiqueta_campo(k)}: se leyó «{campo['crudo']}».",
                accion="Revisa la fecha manualmente. Para una lectura exacta sube el PDF exportado desde la "
                       "computadora en lugar de un escaneo o una imagen.",
                campo=k, pagina=campo.get("pagina"), encontrado=campo["crudo"],
            ))
        elif not campo.get("valido"):
            salida.append(ctx.h(
                "R012", ERROR, "Fecha inválida",
                f"No se pudo interpretar la {etiqueta_campo(k)}: «{campo['crudo']}».",
                accion="Escribe la fecha con el formato dd/mm/aaaa (por ejemplo, 15/02/2027).",
                campo=k, pagina=campo.get("pagina"), encontrado=campo["crudo"],
            ))
    if revisadas and not salida:
        return [ctx.h("R012", OK, "Fechas con formato válido", "Las fechas tienen un formato válido.")]
    return salida


def r013_coherencia_fechas(ctx: ContextoDoc) -> list[Hallazgo]:
    ini, fin = ctx.campo("fecha_inicio"), ctx.campo("fecha_fin")
    if not (ini.get("valido") and fin.get("valido")):
        return []
    d_ini, d_fin = tu.parse_fecha(ini["valor"]), tu.parse_fecha(fin["valor"])
    if d_ini is None or d_fin is None:
        return []
    if d_fin <= d_ini:
        return [ctx.h(
            "R013", ERROR, "Fechas incoherentes",
            f"La fecha de término ({tu.formatear_fecha(fin['valor'])}) es anterior o igual a la de inicio "
            f"({tu.formatear_fecha(ini['valor'])}).",
            accion="Corrige las fechas: el servicio debe terminar después de iniciar.", campo="fecha_fin",
            encontrado=fin["valor"],
        )]
    meses = tu.meses_entre(d_ini, d_fin)
    rango = ctx.req["duracion_meses"]
    if not rango["min"] <= meses <= rango["max"]:
        return [ctx.h(
            "R013", ADVERTENCIA, "Duración fuera de rango",
            f"El periodo dura aproximadamente {meses:.1f} meses y el requisito configurado es de "
            f"{rango['min']} a {rango['max']} meses.",
            accion="Confirma las fechas con tu coordinación de servicio social.", campo="fecha_fin",
            encontrado=round(meses, 1), esperado=f"{rango['min']}-{rango['max']} meses",
        )]
    return [ctx.h("R013", OK, "Periodo coherente", f"El periodo dura aproximadamente {meses:.1f} meses.")]


def r004_horas(ctx: ContextoDoc) -> list[Hallazgo]:
    if not ctx.presente("horas"):
        return []
    campo = ctx.campo("horas")
    if not campo.get("valido"):
        return [ctx.h("R004", ERROR, "Horas ilegibles", f"No se pudo interpretar las horas: «{campo['crudo']}».",
                      accion="Escribe el total de horas como número (por ejemplo, 480).", campo="horas",
                      encontrado=campo["crudo"])]
    requeridas = ctx.req["horas_requeridas"]
    if campo["valor"] == requeridas:
        return [ctx.h("R004", OK, "Horas válidas", f"Total de horas: {campo['valor']}.", campo="horas",
                      pagina=campo.get("pagina"))]
    return [ctx.h(
        "R004", ERROR, "Horas no cumplen el requisito",
        f"Las horas registradas ({campo['valor']}) no coinciden con las requeridas ({requeridas}).",
        accion=f"Verifica el total de horas: el requisito configurado es {requeridas}.",
        campo="horas", pagina=campo.get("pagina"), encontrado=campo["valor"], esperado=requeridas,
    )]


def r006_firmas(ctx: ContextoDoc) -> list[Hallazgo]:
    salida: list[Hallazgo] = []
    obligatoria = {f["id"]: f.get("obligatoria", True) for f in ctx.cfg.get("firmas", [])}
    # En un PDF generado por computadora (sin escanear) se asume que todavía no se imprime ni firma.
    pendiente_en_digital = bool(ctx.cfg.get("firma_digital_pendiente")) and ctx.res["calidad"]["metodo"] == "texto_digital"
    for firma in ctx.res.get("firmas", []):
        etiqueta = firma["etiqueta"]
        if not firma["evaluable"]:
            salida.append(ctx.h(
                "R006", ADVERTENCIA, "No se pudo revisar la firma", firma["motivo"],
                accion="Revisa manualmente que el documento tenga la firma correspondiente.", campo=firma["id"],
            ))
        elif firma["detectada"]:
            salida.append(ctx.h("R006", OK, "Firma detectada", f"Se detectó una firma sobre «{etiqueta}».",
                                campo=firma["id"], pagina=firma.get("pagina")))
        elif obligatoria.get(firma["id"], True) and pendiente_en_digital:
            salida.append(ctx.h(
                "R006", INFO, "Firma pendiente",
                f"El archivo todavía no tiene «{etiqueta}». Es normal si aún no lo imprimes: recábala "
                "cuando ya no haya observaciones.", campo=firma["id"], pagina=firma.get("pagina"),
            ))
        elif obligatoria.get(firma["id"], True):
            salida.append(ctx.h(
                "R006", ADVERTENCIA, "Firma no detectada",
                f"No se detectó una firma en el espacio correspondiente a «{etiqueta}».",
                accion="Verifica que el documento esté firmado en ese espacio. El sistema solo detecta si hay "
                       "tinta; no valida que la firma sea auténtica.",
                campo=firma["id"], pagina=firma.get("pagina"),
            ))
    return salida


# Orden de ejecución de las reglas de contenido.
REGLAS_CONTENIDO: list[Regla] = [
    r001_nombre, r010_obligatorios, r011_matricula, r012_fechas_validas,
    r013_coherencia_fechas, r004_horas, r023_opcion_unica, r006_firmas,
]


def evaluar_documento(tipo: str, resultado: dict[str, Any]) -> list[Hallazgo]:
    """Aplica todas las reglas de un documento sobre su resultado de análisis."""
    cfg = catalogo.formato(tipo, resultado.get("formato", {}).get("version"))
    if cfg is None:
        return []
    ctx = ContextoDoc(tipo=tipo, cfg=cfg, req=catalogo.requisitos(), res=resultado)

    hallazgos = r008_legible(ctx)
    if not resultado["calidad"]["legible"]:  # compuerta: sin lectura confiable no se evalúa nada más
        return hallazgos
    hallazgos += r005_formato(ctx)
    hallazgos += r007_paginas(ctx)
    if not resultado["formato"]["coincide"]:  # documento equivocado: evitar ruido de campos "faltantes"
        return hallazgos
    for regla in REGLAS_CONTENIDO:
        hallazgos += regla(ctx)
    return hallazgos


def documento_utilizable(resultado: dict[str, Any]) -> bool:
    """¿Se puede usar este documento para comparar contra otros?"""
    return bool(resultado["calidad"]["legible"] and resultado["formato"]["coincide"])
