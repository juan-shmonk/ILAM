"""Punto de entrada de la API.

Desarrollo:   uvicorn app.main:app --reload
Documentación interactiva: http://localhost:8000/docs
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import BACKEND_DIR, get_settings
from app.db import init_db
from app.routers import auth, expedientes
from app.services.analysis import ocr


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Prevalidador documental", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)


@app.middleware("http")
async def cabeceras_seguridad(request, call_next):
    respuesta = await call_next(request)
    respuesta.headers.setdefault("X-Content-Type-Options", "nosniff")
    respuesta.headers.setdefault("X-Frame-Options", "DENY")
    respuesta.headers.setdefault("Referrer-Policy", "no-referrer")
    if request.url.path.startswith("/api/"):
        respuesta.headers.setdefault("Cache-Control", "no-store")  # no cachear datos personales
    return respuesta


app.include_router(auth.router)
app.include_router(expedientes.router)


@app.get("/api/salud")
def salud():
    return {"estado": "ok", "ocr_disponible": ocr.ocr_disponible(), "ocr_idioma": ocr.idioma_ocr()}


# Si existe el frontend compilado (frontend/dist), se sirve desde aquí: un solo comando para todo.
_DIST = Path(BACKEND_DIR).parent / "frontend" / "dist"
if _DIST.exists():
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="frontend")
