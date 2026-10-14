"""Modelo de un hallazgo (resultado de aplicar una regla)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

ERROR = "ERROR"
ADVERTENCIA = "ADVERTENCIA"
INFO = "INFO"
OK = "OK"

# Estados del documento / expediente
SIN_OBSERVACIONES = "SIN_OBSERVACIONES"
REQUIERE_CORRECCION = "REQUIERE_CORRECCION"
REVISION_MANUAL = "REVISION_MANUAL"
SIN_DOCUMENTOS = "SIN_DOCUMENTOS"


@dataclass
class Hallazgo:
    """Resultado de una regla.

    Una regla no dice solo "falló": indica qué requisito se incumple, dónde se
    encontró y qué debe hacer el alumno (principio de diseño de la sección 9
    del plan).
    """

    regla: str
    severidad: str
    titulo: str
    mensaje: str
    accion: str = ""
    documento: str | None = None  # tipo de documento al que aplica (o None si es del expediente)
    documentos: list[str] = field(default_factory=list)  # documentos comparados (reglas cruzadas)
    campo: str | None = None
    pagina: int | None = None
    encontrado: Any = None
    esperado: Any = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def estado_de(hallazgos: list[dict[str, Any]]) -> str:
    """Calcula el estado a partir de una lista de hallazgos (como dicts)."""
    if any(h["severidad"] == ERROR for h in hallazgos):
        return REQUIERE_CORRECCION
    if any(h["regla"] == "R008" and h["severidad"] != OK for h in hallazgos):
        return REVISION_MANUAL
    if any(h["severidad"] == ADVERTENCIA for h in hallazgos):
        return REQUIERE_CORRECCION
    return SIN_OBSERVACIONES
