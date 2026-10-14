# Prevalidador documental — Servicio Social (MVP)

Plataforma web que revisa los documentos de servicio social de un alumno **antes** de entregarlos: detecta campos
faltantes, datos que no coinciden entre documentos, firmas ausentes y problemas de formato, y explica qué corregir.
**No sustituye la revisión oficial de la institución.**

MVP con tres documentos: **solicitud**, **carta de aceptación** y **plan de trabajo**.

```
Alumno sube PDF/imagen → texto (PDF digital u OCR) → campos → reglas → comparación entre documentos → reporte
```

Las validaciones son **reglas determinísticas y explicables** (no dependen de una IA). La IA (LLM/ML) se agregará
después como complemento; ver [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md).

## Requisitos (Windows)

| Programa | Versión | Para qué |
|---|---|---|
| Python | 3.11 o superior | backend |
| Node.js | 18 o superior (recomendado 20+) | frontend |
| Tesseract OCR | 5.x (opcional) | leer **fotos y escaneos**. Los PDF con texto digital NO lo necesitan |

No hace falta instalar PostgreSQL, Docker ni Redis: la base de datos es SQLite (un archivo dentro de `backend/data/`).

## Puesta en marcha

Abre PowerShell dentro de la carpeta `prevalidador`.

**1. Backend**

```powershell
cd backend
py -m venv .venv
.venv\Scripts\Activate.ps1          # si da error de permisos: Set-ExecutionPolicy -Scope Process Bypass
pip install -r requirements.txt
python -m scripts.generar_muestras  # crea documentos de prueba en backend\samples
uvicorn app.main:app --reload
```

La API queda en <http://localhost:8000> y su documentación interactiva en <http://localhost:8000/docs>.

**2. Frontend** (otra ventana de PowerShell)

```powershell
cd frontend
npm install
npm run dev
```

Abre <http://localhost:5173>, crea una cuenta, crea un expediente y sube los tres PDF de
`backend\samples\01_correcto` (o de cualquier otro escenario para ver cómo se detectan los errores).

**Alternativa de un solo servidor:** ejecuta `npm run build` en `frontend` y luego solo `uvicorn app.main:app`;
la aplicación completa queda en <http://localhost:8000>.

## Pruebas y evaluación

```powershell
cd backend
pip install -r requirements-dev.txt
python -m pytest              # pruebas automáticas
python -m scripts.evaluar     # precisión / recall contra los documentos de muestra
```

`evaluar` compara lo que detecta el sistema contra la respuesta correcta (`ground_truth.json`) de cada expediente.
Con los documentos sintéticos incluidos da 100 %, **lo cual es esperable porque los generó el mismo proyecto**;
el número que importa es el que salga con los documentos que creen tus compañeros y, después, con formatos reales.

## Activar el OCR (opcional)

1. Instala Tesseract para Windows (build de UB Mannheim) y marca el idioma **Spanish** durante la instalación.
2. Si `tesseract` no queda en el PATH, copia `backend\.env.example` como `backend\.env` y define
   `PREVAL_TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe`.
3. Reinicia el backend. Si funciona, `http://localhost:8000/api/salud` muestra `"ocr_disponible": true`.

Sin OCR, subir una foto o un escaneo resulta en «Documento no legible» y el estado **Revisión manual**; nada se rompe.

## Estructura

```
prevalidador/
├── backend/
│   ├── app/
│   │   ├── main.py, config.py, db.py, models.py, security.py, deps.py
│   │   ├── routers/            auth, expedientes (subida, reportes, descarga)
│   │   ├── config_docs/        JSON: tipos de documento y requisitos  ← se edita sin tocar código
│   │   └── services/
│   │       ├── analysis/       texto (PDF/OCR), extractores, normalizadores, firmas, pipeline
│   │       ├── rules/          reglas por documento y entre documentos, modelo de hallazgo
│   │       ├── report.py       reporte + JSON canónico del expediente
│   │       └── storage.py      almacenamiento de archivos
│   ├── scripts/                generar_muestras.py, evaluar.py
│   └── tests/
├── frontend/                   React + Vite + TypeScript
└── docs/                       arquitectura, catálogo de reglas, guía para documentos sintéticos
```

## Qué debes confirmar antes de usarlo en serio

Los valores de `backend/app/config_docs/requisitos.json` (480 horas, duración de 6 a 24 meses, formato de matrícula)
y los encabezados/etiquetas de cada documento son **ejemplos**. Deben confirmarse contra el reglamento y los formatos
oficiales vigentes. Se cambian ahí, en JSON, sin modificar código.

## Seguridad (lo que ya está y lo que falta)

Ya está: contraseñas con argon2; sesión en cookie `httpOnly`; cada expediente y archivo solo es accesible por su dueño
(404 para los demás); archivos con nombre aleatorio y tipo verificado por contenido; límite de tamaño; bitácora de
auditoría; sin claves en el código.

Falta para producción real: HTTPS (`PREVAL_COOKIE_SECURE=true`), cifrado de archivos en reposo, política de retención y
borrado, aviso de privacidad, limitación de intentos persistente (ahora es en memoria) y anonimización antes de usar
documentos reales en Machine Learning.
