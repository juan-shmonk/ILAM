"""Contraseñas (argon2) y sesiones (JWT firmado en cookie httpOnly)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.config import get_secret_key, get_settings

COOKIE_NAME = "prevalidador_sesion"
_hasher = PasswordHasher()
# Hash de relleno para gastar el mismo tiempo cuando el correo no existe (evita enumerar usuarios).
_HASH_FALSO = _hasher.hash("contraseña-de-relleno")


def hashear_password(password: str) -> str:
    return _hasher.hash(password)


def verificar_password(password: str, hash_guardado: str | None) -> bool:
    try:
        return _hasher.verify(hash_guardado or _HASH_FALSO, password) and hash_guardado is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def crear_token(usuario_id: int) -> str:
    ahora = datetime.now(timezone.utc)
    payload = {
        "sub": str(usuario_id),
        "iat": ahora,
        "exp": ahora + timedelta(hours=get_settings().session_hours),
    }
    return jwt.encode(payload, get_secret_key(), algorithm="HS256")


def leer_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, get_secret_key(), algorithms=["HS256"])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
