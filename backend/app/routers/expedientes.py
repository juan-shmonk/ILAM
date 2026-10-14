"""Expedientes, subida de documentos y reportes de prevalidación."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.config import get_settings
from app.db import get_db
from app.deps import expediente_propio, registrar, usuario_actual
from app.services import catalogo
from app.services.analysis.pipeline import analizar_documento
from app.services.report import VERSION_MOTOR, construir_reporte
from app.services.storage import TIPOS_PERMITIDOS, AlmacenLocal, detectar_mime

log = logging.getLogger("prevalidador")
router = APIRouter(prefix="/api", tags=["expedientes"])


def _almacen() -> AlmacenLocal:
    return AlmacenLocal(get_settings().storage_dir)


def _doc_json(d: models.Documento) -> dict[str, Any]:
    return {
        "id": d.id, "tipo": d.tipo, "version": d.version, "activo": d.activo,
        "archivo": d.nombre_original, "mime": d.mime, "tamano": d.tamano, "creado_en": d.creado_en.isoformat(),
    }


def _ultimo_reporte(exp: models.Expediente) -> models.Reporte | None:
    return exp.reportes[-1] if exp.reportes else None


def _regenerar_reporte(db: Session, exp: models.Expediente) -> dict[str, Any]:
    """Recalcula el reporte con los documentos activos y lo guarda en el historial."""
    db.expire_all()  # asegura leer los análisis recién guardados
    docs = []
    for d in exp.documentos:
        if not d.activo or not d.analisis:
            continue
        docs.append({"id": d.id, "tipo": d.tipo, "version": d.version, "nombre_original": d.nombre_original,
                     "resultado": d.analisis[-1].resultado})
    contenido = construir_reporte(exp.id, exp.tramite, docs)
    db.add(models.Reporte(expediente_id=exp.id, estado=contenido["estado"], contenido=contenido))
    db.commit()
    db.refresh(exp)
    return contenido


# ---------------------------------------------------------------- catálogo
@router.get("/tipos-documento")
def tipos_documento(_: models.Usuario = Depends(usuario_actual)):
    return [
        {"codigo": c, "nombre": t["nombre"], "descripcion": t["descripcion"],
         "campos": [{"clave": k, "obligatorio": v.get("obligatorio", False)} for k, v in t["campos"].items()],
         "firmas": [f["etiqueta"] for f in t.get("firmas", [])]}
        for c, t in catalogo.tipos_documento().items()
    ]


# ------------------------------------------------------------- expedientes
@router.post("/expedientes", status_code=status.HTTP_201_CREATED)
def crear_expediente(db: Session = Depends(get_db), usuario: models.Usuario = Depends(usuario_actual)):
    exp = models.Expediente(usuario_id=usuario.id)
    db.add(exp)
    db.commit()
    registrar(db, usuario.id, "expediente_creado", "expediente", exp.id)
    return {"id": exp.id, "tramite": exp.tramite, "creado_en": exp.creado_en.isoformat()}


@router.get("/expedientes")
def listar_expedientes(db: Session = Depends(get_db), usuario: models.Usuario = Depends(usuario_actual)):
    exps = db.scalars(
        select(models.Expediente).where(models.Expediente.usuario_id == usuario.id).order_by(models.Expediente.id.desc())
    ).all()
    salida = []
    for e in exps:
        ultimo = _ultimo_reporte(e)
        salida.append({
            "id": e.id, "tramite": e.tramite, "creado_en": e.creado_en.isoformat(),
            "documentos": sum(1 for d in e.documentos if d.activo),
            "estado": ultimo.estado if ultimo else "SIN_DOCUMENTOS",
        })
    return salida


@router.get("/expedientes/{expediente_id}")
def detalle_expediente(expediente_id: int, db: Session = Depends(get_db),
                       usuario: models.Usuario = Depends(usuario_actual)):
    exp = expediente_propio(expediente_id, db, usuario)
    ultimo = _ultimo_reporte(exp)
    return {
        "id": exp.id, "tramite": exp.tramite, "creado_en": exp.creado_en.isoformat(),
        "documentos": [_doc_json(d) for d in exp.documentos if d.activo],
        "reporte": ultimo.contenido if ultimo else None,
    }


@router.get("/expedientes/{expediente_id}/historial")
def historial(expediente_id: int, db: Session = Depends(get_db), usuario: models.Usuario = Depends(usuario_actual)):
    exp = expediente_propio(expediente_id, db, usuario)
    return [{"id": r.id, "estado": r.estado, "creado_en": r.creado_en.isoformat(),
             "conteos": r.contenido.get("conteos")} for r in reversed(exp.reportes)]


@router.post("/expedientes/{expediente_id}/revalidar")
def revalidar(expediente_id: int, db: Session = Depends(get_db), usuario: models.Usuario = Depends(usuario_actual)):
    exp = expediente_propio(expediente_id, db, usuario)
    contenido = _regenerar_reporte(db, exp)
    registrar(db, usuario.id, "expediente_revalidado", "expediente", exp.id)
    return contenido


@router.get("/expedientes/{expediente_id}/json")
def expediente_json(expediente_id: int, db: Session = Depends(get_db),
                    usuario: models.Usuario = Depends(usuario_actual)):
    """Estructura canónica del expediente (la que comparan las reglas)."""
    exp = expediente_propio(expediente_id, db, usuario)
    ultimo = _ultimo_reporte(exp)
    if ultimo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Aún no hay documentos analizados.")
    return ultimo.contenido["expediente_json"]


# --------------------------------------------------------------- documentos
@router.post("/expedientes/{expediente_id}/documentos", status_code=status.HTTP_201_CREATED)
def subir_documento(
    expediente_id: int,
    tipo: str = Form(...),
    archivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    usuario: models.Usuario = Depends(usuario_actual),
):
    exp = expediente_propio(expediente_id, db, usuario)
    if catalogo.tipo(tipo) is None:
        raise HTTPException(422, "Tipo de documento desconocido.")

    limite = get_settings().max_upload_mb * 1024 * 1024
    contenido = archivo.file.read(limite + 1)
    if not contenido:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "El archivo está vacío.")
    if len(contenido) > limite:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            f"El archivo supera el máximo de {get_settings().max_upload_mb} MB.")
    mime = detectar_mime(contenido[:16])
    if mime not in TIPOS_PERMITIDOS:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Solo se aceptan archivos PDF, PNG o JPG.")

    almacen = _almacen()
    clave, sha = almacen.guardar(contenido, mime)

    previos = [d for d in exp.documentos if d.tipo == tipo]
    for p in previos:
        p.activo = False
    nombre = (archivo.filename or "documento")[:255]
    doc = models.Documento(
        expediente_id=exp.id, tipo=tipo, version=len(previos) + 1, activo=True, nombre_original=nombre,
        clave_almacenamiento=clave, sha256=sha, mime=mime, tamano=len(contenido),
    )
    db.add(doc)
    db.commit()

    error_interno = None
    try:
        resultado = analizar_documento(almacen.ruta(clave), mime, tipo).to_dict()
    except Exception as exc:  # un archivo raro no debe tumbar el servidor
        log.exception("Error analizando el documento %s", doc.id)
        error_interno = f"{type(exc).__name__}: {exc}"
        resultado = {
            "tipo": tipo, "formato": {"esperado": tipo, "detectado": None, "coincide": False},
            "campos": {}, "firmas": [],
            "calidad": {"metodo": "ninguno", "n_paginas": 0, "caracteres": 0, "confianza_ocr": None,
                        "nitidez": None, "ocr_disponible": False, "legible": False, "avisos": [],
                        "motivo": "Ocurrió un error al analizar el archivo. Intenta subirlo de nuevo o usa otro formato."},
        }
    db.add(models.Analisis(documento_id=doc.id, resultado=resultado, version_motor=VERSION_MOTOR,
                           error_interno=error_interno))
    db.commit()
    db.refresh(exp)

    registrar(db, usuario.id, "documento_subido", "documento", doc.id,
              {"tipo": tipo, "sha256": sha, "tamano": len(contenido), "version": doc.version})
    reporte = _regenerar_reporte(db, exp)
    return {"documento": _doc_json(doc), "reporte": reporte}


@router.get("/documentos/{documento_id}/archivo")
def descargar_documento(documento_id: int, db: Session = Depends(get_db),
                        usuario: models.Usuario = Depends(usuario_actual)):
    doc = db.get(models.Documento, documento_id)
    if doc is None or doc.expediente.usuario_id != usuario.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Documento no encontrado.")
    ruta = _almacen().ruta(doc.clave_almacenamiento)
    if not ruta.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El archivo ya no está disponible.")
    registrar(db, usuario.id, "documento_descargado", "documento", doc.id)
    return FileResponse(ruta, media_type=doc.mime, filename=doc.nombre_original, content_disposition_type="inline")
