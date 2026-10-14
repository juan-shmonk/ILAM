from datetime import date

import pytest

from app.services.analysis import textutil as tu


@pytest.mark.parametrize("texto,esperado", [
    ("15/02/2027", date(2027, 2, 15)),
    ("15-02-2027", date(2027, 2, 15)),
    ("5.2.27", date(2027, 2, 5)),
    ("2027-02-15", date(2027, 2, 15)),
    ("15 de febrero de 2027", date(2027, 2, 15)),
    ("15. de Agosto del 2027", date(2027, 8, 15)),
    ("1 de setiembre 2027", date(2027, 9, 1)),
    ("31/02/2027", None),  # día inexistente
    ("sin fecha", None),
    ("", None),
])
def test_parse_fecha(texto, esperado):
    assert tu.parse_fecha(texto) == esperado


def test_formatear_fecha():
    assert tu.formatear_fecha("2027-02-05") == "05/02/2027"
    assert tu.formatear_fecha(None) == "(vacío)"


@pytest.mark.parametrize("texto,esperado", [("480 horas", 480), ("1,200", 1200), ("480*", 480), ("abc", None)])
def test_parse_entero(texto, esperado):
    assert tu.parse_entero(texto) == esperado


def test_nombres_se_comparan_sin_acentos_orden_ni_titulos():
    assert tu.normalizar_nombre("Lic. María Pérez López") == "maria perez lopez"
    assert tu.normalizar_nombre("PÉREZ  LÓPEZ, María") == "perez lopez maria"
    assert tu.normalizar_matricula("2153-0177 ") == "21530177"


def test_meses_calendario():
    assert tu.meses_entre(date(2027, 2, 15), date(2027, 8, 15)) == pytest.approx(6.0)
    assert tu.meses_entre(date(2027, 2, 15), date(2027, 8, 1)) < 6
