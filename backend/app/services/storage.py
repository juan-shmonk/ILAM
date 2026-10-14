"""Almacenamiento de documentos en disco local.

Los archivos se guardan con nombre aleatorio (UUID), nunca con el nombre que
subió el usuario, y nunca se sirven de forma pública: la descarga siempre pasa
por la API, que comprueba que el archivo pertenezca al usuario.

``AlmacenLocal`` es la única clase que toca el disco. Para usar S3/MinIO más
adelante basta con escribir otra clase con los mismos métodos.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path

TIPOS_PERMITIDOS = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
}
_RE_CLAVE = re.compile(r"^[0-9a-f]{32}\.(pdf|png|jpg)$")


def detectar_mime(inicio: bytes) -> str | None:
    """Detecta el tipo real por los primeros bytes (no confía en la extensión)."""
    if inicio.startswith(b"%PDF-"):
        return "application/pdf"
    if inicio.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if inicio.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    return None


def detectar_mime_archivo(ruta: Path) -> str | None:
    with open(ruta, "rb") as f:
        return detectar_mime(f.read(16))


class AlmacenLocal:
    def __init__(self, base: Path):
        self.base = Path(base)
        self.base.mkdir(parents=True, exist_ok=True)

    def guardar(self, contenido: bytes, mime: str) -> tuple[str, str]:
        """Guarda los bytes y devuelve (clave, sha256)."""
        clave = f"{uuid.uuid4().hex}{TIPOS_PERMITIDOS[mime]}"
        (self.base / clave).write_bytes(contenido)
        return clave, hashlib.sha256(contenido).hexdigest()

    def ruta(self, clave: str) -> Path:
        if not _RE_CLAVE.match(clave):  # evita rutas del tipo ../../algo
            raise ValueError("Clave de almacenamiento inválida")
        return self.base / clave

    def eliminar(self, clave: str) -> None:
        self.ruta(clave).unlink(missing_ok=True)
