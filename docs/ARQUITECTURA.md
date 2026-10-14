# Arquitectura

## Principio

> La IA interpreta y detecta; las reglas oficiales determinan los requisitos; la decisión final es de las personas.

Toda validación administrativa es una **regla determinística y explicable**. La IA solo se usará donde las reglas no
llegan (leer documentos difíciles, explicar en lenguaje natural, priorizar revisiones).

## Flujo

```
                 ┌───────────────────────── backend (FastAPI) ──────────────────────────┐
 React ──HTTP──► │ auth ─► expediente ─► subir documento                                │
 (Vite)          │                          │                                           │
                 │            storage ◄─────┤ guarda archivo (UUID, sha256)             │
                 │                          ▼                                           │
                 │  analysis/pipeline: texto (PDF digital | OCR) ─► compuerta legibilidad│
                 │        ─► formato (título) ─► extractores (JSON config) ─► firmas     │
                 │                          │  resultado JSON  ──► tabla analisis       │
                 │                          ▼                                           │
                 │  rules/documento  +  rules/cruzadas  ─► hallazgos                    │
                 │                          ▼                                           │
                 │  report: estado, resumen, comparación, JSON canónico ─► tabla reportes│
                 └───────────────────────────────────────────────────────────────────────┘
```

Todo el análisis corre dentro de la petición de subida (segundos). Si más adelante tarda demasiado, `analizar_documento`
se mueve a una cola sin cambiar nada más.

## Dónde se usa JSON

| Uso | Archivo / tabla |
|---|---|
| Definición de cada documento (etiquetas, campos, firmas, páginas) | `app/config_docs/*.json` |
| Requisitos del trámite (horas, duración, documento base por campo, umbrales) | `app/config_docs/requisitos.json` |
| Resultado del análisis de un archivo | `analisis.resultado` (columna JSON) |
| Reporte de prevalidación (historial) | `reportes.contenido` (columna JSON) |
| Estructura canónica del expediente (sección 8 del plan) | `reporte.expediente_json`, endpoint `GET /api/expedientes/{id}/json` |
| Respuesta correcta de documentos de prueba | `samples/*/ground_truth.json` |

## Modelo de datos

```
usuarios ─< expedientes ─< documentos ─< analisis
                       └─< reportes
auditoria (usuario, acción, entidad, detalle)
```

- `documentos`: una fila por archivo subido; `version` y `activo` (solo la última versión de cada tipo está activa).
- `analisis`: qué se leyó del archivo (calidad, formato, campos con valor crudo y normalizado, firmas).
- `reportes`: cada vez que cambia el expediente se guarda una instantánea (historial).

## Decisiones frente al plan original

| Plan | Decisión | Motivo |
|---|---|---|
| PostgreSQL / Supabase | **SQLite** vía SQLAlchemy | proyecto de materia, corre en cualquier PC sin instalar nada; migrar a Postgres es cambiar `PREVAL_DATABASE_URL` e instalar el driver |
| Next.js | **React + Vite** | no se necesita SSR; menos piezas |
| Vercel + API gestionada | local; después un VPS o servidor institucional | el OCR es procesamiento largo, no encaja en funciones serverless |
| Object storage | carpeta local tras la clase `AlmacenLocal` | se cambia por S3/MinIO reemplazando una clase |
| ML en el flujo | fuera del camino crítico | sin datos etiquetados no hay problema de ML bien definido |

## Cómo se conectarán las capas de IA (fase 2 y 3)

- **LLM para explicaciones:** `report.redactar()` genera hoy el resumen con plantillas. Un LLM se conecta ahí,
  recibiendo *solo* los hallazgos ya calculados (regla, valor encontrado, esperado, documento) y devolviendo texto.
  Nunca decide si algo es error. Antes de enviar texto a un servicio externo se debe seudonimizar (nombre, matrícula).
- **LLM para extraer campos:** cuando el extractor por etiquetas no encuentra un campo, `extraer_campos` puede llamar a
  un modelo (local con Ollama, o externo) pidiendo JSON con el esquema de `config_docs`, y marcar `fuente: "llm"`.
- **ML:** primero auditar los datos históricos (qué contienen, etiquetas de aceptado/rechazado, motivos). Con pocos
  ejemplos se usan modelos clásicos (regresión logística, gradient boosting) sobre variables como `campos_vacíos`,
  `firma_detectada`, `similitud_de_nombre`; el resultado sería una **prioridad de revisión**, nunca un veredicto.

## Limitaciones conocidas

- La detección de firmas mide presencia de tinta en la zona sobre la etiqueta; no valida autenticidad y puede fallar
  con firmas muy tenues o fotos con sombras. Por eso es una **advertencia**, no un error.
- Los extractores esperan líneas del tipo `Etiqueta: valor`. Formatos oficiales con tablas o texto corrido requerirán
  patrones adicionales en el JSON (o el extractor con LLM).
- Con el mismo documento base, un solo dato equivocado puede producir varias observaciones (una por cada documento que
  difiere). Es intencional, pero se puede agrupar más adelante.
