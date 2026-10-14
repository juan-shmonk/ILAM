"""Registro, inicio y cierre de sesión."""

from __future__ import annotations

import time
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.config import get_settings
from app.db import get_db
from app.deps import registrar, usuario_actual
from app.security import COOKIE_NAME, crear_token, hashear_password, verificar_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

EMAIL_PATRON = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"

# Limitador simple en memoria: máx. 5 intentos fallidos por correo cada 15 minutos.
_INTENTOS: dict[str, list[float]] = defaultdict(list)
_VENTANA_S, _MAX_INTENTOS = 15 * 60, 5


class RegistroIn(BaseModel):
    email: str = Field(pattern=EMAIL_PATRON, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    nombre: str = Field(min_length=2, max_length=200)


class LoginIn(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(max_length=128)


def _usuario_json(u: models.Usuario) -> dict:
    return {"id": u.id, "email": u.email, "nombre": u.nombre, "rol": u.rol}


def _poner_cookie(response: Response, usuario_id: int) -> None:
    s = get_settings()
    response.set_cookie(
        COOKIE_NAME, crear_token(usuario_id), httponly=True, samesite="lax",
        secure=s.cookie_secure, max_age=s.session_hours * 3600, path="/",
    )


@router.post("/registro", status_code=status.HTTP_201_CREATED)
def registro(datos: RegistroIn, response: Response, db: Session = Depends(get_db)):
    email = datos.email.strip().lower()
    if db.scalar(select(models.Usuario).where(models.Usuario.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe una cuenta con ese correo.")
    usuario = models.Usuario(email=email, nombre=datos.nombre.strip(), password_hash=hashear_password(datos.password))
    db.add(usuario)
    db.commit()
    registrar(db, usuario.id, "registro", "usuario", usuario.id)
    _poner_cookie(response, usuario.id)
    return _usuario_json(usuario)


@router.post("/login")
def login(datos: LoginIn, response: Response, db: Session = Depends(get_db)):
    email = datos.email.strip().lower()
    ahora = time.time()
    _INTENTOS[email] = [t for t in _INTENTOS[email] if ahora - t < _VENTANA_S]
    if len(_INTENTOS[email]) >= _MAX_INTENTOS:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Demasiados intentos. Espera unos minutos.")
    usuario = db.scalar(select(models.Usuario).where(models.Usuario.email == email))
    if not verificar_password(datos.password, usuario.password_hash if usuario else None):
        _INTENTOS[email].append(ahora)
        registrar(db, usuario.id if usuario else None, "login_fallido", detalle={"email": email})
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Correo o contraseña incorrectos.")
    _INTENTOS.pop(email, None)
    registrar(db, usuario.id, "login", "usuario", usuario.id)
    _poner_cookie(response, usuario.id)
    return _usuario_json(usuario)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    return None


@router.get("/yo")
def yo(usuario: models.Usuario = Depends(usuario_actual)):
    return _usuario_json(usuario)
