"""Pruebas de la API: autenticación, aislamiento entre usuarios y flujo completo."""

from pathlib import Path

DOCS = {"solicitud": "solicitud.pdf", "carta_aceptacion": "carta_aceptacion.pdf", "plan_trabajo": "plan_trabajo.pdf"}


def _registrar(cliente, email="ana@example.com"):
    r = cliente.post("/api/auth/registro", json={"email": email, "password": "una-clave-segura", "nombre": "Ana Prueba"})
    assert r.status_code == 201, r.text
    return r


def _subir(cliente, exp_id, ruta: Path, tipo: str):
    with open(ruta, "rb") as f:
        return cliente.post(f"/api/expedientes/{exp_id}/documentos", data={"tipo": tipo},
                            files={"archivo": (ruta.name, f, "application/pdf")})


def test_requiere_sesion(cliente):
    assert cliente.get("/api/expedientes").status_code == 401
    assert cliente.post("/api/expedientes").status_code == 401


def test_cookie_httponly_y_login(cliente):
    r = _registrar(cliente, "cookie@example.com")
    assert "httponly" in r.headers["set-cookie"].lower()
    cliente.post("/api/auth/logout")
    assert cliente.get("/api/auth/yo").status_code == 401
    assert cliente.post("/api/auth/login", json={"email": "cookie@example.com", "password": "mala"}).status_code == 401
    ok = cliente.post("/api/auth/login", json={"email": "cookie@example.com", "password": "una-clave-segura"})
    assert ok.status_code == 200


def test_flujo_completo_con_errores(cliente, muestras):
    _registrar(cliente, "flujo@example.com")
    exp = cliente.post("/api/expedientes").json()
    carpeta = muestras / "16_varios_errores"
    ultimo = None
    for tipo, archivo in DOCS.items():
        r = _subir(cliente, exp["id"], carpeta / archivo, tipo)
        assert r.status_code == 201, r.text
        ultimo = r.json()
    assert ultimo["reporte"]["estado"] == "REQUIERE_CORRECCION"
    assert ultimo["reporte"]["conteos"]["errores"] >= 2

    detalle = cliente.get(f"/api/expedientes/{exp['id']}").json()
    assert len(detalle["documentos"]) == 3
    assert cliente.get(f"/api/expedientes/{exp['id']}/json").json()["expediente"]["servicio"]["horas"] == 400  # el plan (fuente base de las horas) dice 400
    assert len(cliente.get(f"/api/expedientes/{exp['id']}/historial").json()) == 3


def test_reemplazar_documento_crea_version_y_corrige(cliente, muestras):
    _registrar(cliente, "version@example.com")
    exp = cliente.post("/api/expedientes").json()
    mal, bien = muestras / "05_horas_incorrectas", muestras / "01_correcto"
    for tipo, archivo in DOCS.items():
        _subir(cliente, exp["id"], mal / archivo, tipo)
    assert cliente.get(f"/api/expedientes/{exp['id']}").json()["reporte"]["estado"] == "REQUIERE_CORRECCION"
    r = _subir(cliente, exp["id"], bien / "plan_trabajo.pdf", "plan_trabajo")  # sube el plan corregido
    assert r.json()["documento"]["version"] == 2
    assert r.json()["reporte"]["estado"] == "SIN_OBSERVACIONES"


def test_aislamiento_entre_usuarios(cliente, muestras):
    from fastapi.testclient import TestClient

    from app.main import app

    _registrar(cliente, "duena@example.com")
    exp = cliente.post("/api/expedientes").json()
    doc = _subir(cliente, exp["id"], muestras / "01_correcto" / "solicitud.pdf", "solicitud").json()["documento"]

    with TestClient(app) as otro:
        _registrar(otro, "intruso@example.com")
        assert otro.get(f"/api/expedientes/{exp['id']}").status_code == 404
        assert otro.get(f"/api/expedientes/{exp['id']}/json").status_code == 404
        assert otro.get(f"/api/documentos/{doc['id']}/archivo").status_code == 404
        assert otro.get("/api/expedientes").json() == []
        assert _subir(otro, exp["id"], muestras / "01_correcto" / "solicitud.pdf", "solicitud").status_code == 404

    assert cliente.get(f"/api/documentos/{doc['id']}/archivo").status_code == 200


def test_rechaza_archivos_no_permitidos(cliente):
    _registrar(cliente, "malo@example.com")
    exp = cliente.post("/api/expedientes").json()
    r = cliente.post(f"/api/expedientes/{exp['id']}/documentos", data={"tipo": "solicitud"},
                     files={"archivo": ("virus.pdf", b"MZ\x90\x00 esto no es un pdf", "application/pdf")})
    assert r.status_code == 415
    r = cliente.post(f"/api/expedientes/{exp['id']}/documentos", data={"tipo": "inexistente"},
                     files={"archivo": ("a.pdf", b"%PDF-1.4", "application/pdf")})
    assert r.status_code == 422


def test_pdf_corrupto_se_reporta_como_ilegible(cliente):
    _registrar(cliente, "corrupto@example.com")
    exp = cliente.post("/api/expedientes").json()
    r = cliente.post(f"/api/expedientes/{exp['id']}/documentos", data={"tipo": "solicitud"},
                     files={"archivo": ("roto.pdf", b"%PDF-1.4 basura basura", "application/pdf")})
    assert r.status_code == 201
    assert r.json()["reporte"]["estado"] == "REVISION_MANUAL"
