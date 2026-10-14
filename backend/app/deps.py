"""Dependencias de FastAPI: usuario actual y control de acceso a expedientes."""

from __future__ import annotations

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import models
from app.db import get_db
from app.security import COOKIE_NAME, leer_token


def usuario_actual(
    sesion: str | None = Cookie(default=None, alias=COOKIE_NAME),
    db: Session = Depends(get_db),
) -> models.Usuario:
    usuario_id = leer_token(sesion) if sesion else None
    usuario = db.get(models.Usuario, usuario_id) if usuario_id else None
    if usuario is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Inicia sesión para continuar.")
    return usuario


def expediente_propio(expediente_id: int, db: Session, usuario: models.Usuario) -> models.Expediente:
    """Devuelve el expediente solo si es del usuario. Si no, responde 404 (no revela que existe)."""
    exp = db.get(models.Expediente, expediente_id)
    if exp is None or exp.usuario_id != usuario.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Expediente no encontrado.")
    return exp


def registrar(db: Session, usuario_id: int | None, accion: str, entidad: str | None = None,
              entidad_id: int | None = None, detalle: dict | None = None) -> None:
    """Guarda una acción importante en la bitácora de auditoría."""
    db.add(models.Auditoria(usuario_id=usuario_id, accion=accion, entidad=entidad,
                            entidad_id=entidad_id, detalle=detalle))
    db.commit()
