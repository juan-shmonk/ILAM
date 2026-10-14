"""Modelo de datos (SQLAlchemy 2).

users ─< expedientes ─< documentos ─< analisis
                   └─< reportes
auditoria (acciones importantes, con el usuario que las hizo)

Los datos variables (campos extraídos, hallazgos) se guardan como JSON; el
resto de columnas son relacionales para poder consultar y filtrar.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    nombre: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(255))
    rol: Mapped[str] = mapped_column(String(20), default="alumno")  # alumno | revisor | admin
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)

    expedientes: Mapped[list["Expediente"]] = relationship(back_populates="usuario")


class Expediente(Base):
    __tablename__ = "expedientes"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    tramite: Mapped[str] = mapped_column(String(50), default="servicio_social")
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)

    usuario: Mapped[Usuario] = relationship(back_populates="expedientes")
    documentos: Mapped[list["Documento"]] = relationship(back_populates="expediente", order_by="Documento.id")
    reportes: Mapped[list["Reporte"]] = relationship(back_populates="expediente", order_by="Reporte.id")


class Documento(Base):
    __tablename__ = "documentos"

    id: Mapped[int] = mapped_column(primary_key=True)
    expediente_id: Mapped[int] = mapped_column(ForeignKey("expedientes.id"), index=True)
    tipo: Mapped[str] = mapped_column(String(50))  # solicitud | carta_aceptacion | plan_trabajo
    version: Mapped[int] = mapped_column(Integer, default=1)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)  # solo la última versión está activa
    nombre_original: Mapped[str] = mapped_column(String(255))
    clave_almacenamiento: Mapped[str] = mapped_column(String(80))
    sha256: Mapped[str] = mapped_column(String(64))
    mime: Mapped[str] = mapped_column(String(50))
    tamano: Mapped[int] = mapped_column(Integer)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)

    expediente: Mapped[Expediente] = relationship(back_populates="documentos")
    analisis: Mapped[list["Analisis"]] = relationship(back_populates="documento", order_by="Analisis.id")


class Analisis(Base):
    """Resultado de analizar un archivo: calidad, formato, campos y firmas (JSON)."""

    __tablename__ = "analisis"

    id: Mapped[int] = mapped_column(primary_key=True)
    documento_id: Mapped[int] = mapped_column(ForeignKey("documentos.id"), index=True)
    resultado: Mapped[dict[str, Any]] = mapped_column(JSON)
    version_motor: Mapped[str] = mapped_column(String(20))
    error_interno: Mapped[str | None] = mapped_column(Text, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)

    documento: Mapped[Documento] = relationship(back_populates="analisis")


class Reporte(Base):
    """Instantánea del reporte de prevalidación (historial de resultados)."""

    __tablename__ = "reportes"

    id: Mapped[int] = mapped_column(primary_key=True)
    expediente_id: Mapped[int] = mapped_column(ForeignKey("expedientes.id"), index=True)
    estado: Mapped[str] = mapped_column(String(30))
    contenido: Mapped[dict[str, Any]] = mapped_column(JSON)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)

    expediente: Mapped[Expediente] = relationship(back_populates="reportes")


class Auditoria(Base):
    __tablename__ = "auditoria"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True, index=True)
    accion: Mapped[str] = mapped_column(String(60))
    entidad: Mapped[str | None] = mapped_column(String(40), nullable=True)
    entidad_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detalle: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)
