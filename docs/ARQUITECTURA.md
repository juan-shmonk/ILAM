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
                 │   ─► formato (título + versión) ─► extractor por zonas o etiquetas ─► firmas│
                 │                          │  resultado JSON  ──► tabla analisis       │
                 │                          ▼                                           │
                 │  rules/documento  +  rules/cruzadas  ─► hallazgos                    │
                 │                          ▼                                           │
                 │  report: estado, resumen, comparación, JSON canónico ─► tabla reportes│
                 └───────────────────────────────────────────────────────────────────────┘
```

Todo el análisis corre dentro de la petición de subida (segundos). Si más adelante tarda demasiado, `analizar_documento`
se mueve a una cola sin cambiar nada más.

## Formatos y extracción por zonas

Un tipo de documento puede tener varias **versiones de formato** (un archivo `config_docs/*.json` cada una, con
`codigo`, `formato` e `identificadores`). `catalogo.elegir_formato` escoge la versión según el texto leído:

| Archivo | Formato | Extracción |
|---|---|---|
| `solicitud.json` | Oficial ITC-VI-PO-002-02 rev. 0 (principal) | zonas |
| `plan_trabajo.json` | Oficial ITC-VI-PO-002-07 rev. 0 (principal) | zonas |
| `*_sintetico.json` | Sintéticos de prueba (`samples/`) | etiquetas `Etiqueta: valor` |

Los formatos oficiales se diseñaron para llenarse a mano (líneas `____` con marcas `(n)`), y al llenarlos en Google
Docs muchos valores quedan como **imágenes pegadas** sobre la línea. Por eso `analysis/plantilla.py`:

1. Obtiene las palabras con posición (texto digital, o el OCR de la página si es escaneo/foto) y separa lo que el
   procesador de texto pegó (`22530305______Carrera:` → `22530305` + `Carrera:`).
2. Busca el **ancla** de cada campo (la marca `(5)` o una etiqueta) y calcula su **zona**: a la derecha hasta la
   siguiente etiqueta, debajo hasta otra marca, o una caja relativa. Las medidas van en alturas del ancla.
3. Lee la zona: palabras digitales + **OCR de cada imagen incrustada** en ella (la imagen original, sin la línea de
   guiones que confunde al OCR), intercaladas por posición. En escaneos usa las palabras del OCR de la página.
4. Firmas y sello: mide tinta en una caja relativa al ancla (`(8)`, `(9)`, `(10)`), sin texto impreso, líneas ni
   bordes de tabla.

Si la institución cambia el formato, se agrega un JSON nuevo con otro `formato`; los expedientes anteriores siguen
evaluándose con su versión (`analisis.resultado.formato.version`).

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
- La lectura por zonas depende de que el formato conserve sus marcas `(n)`. Un PDF exportado desde la computadora se
  lee de forma exacta; en escaneos y fotos el OCR puede fallar con marcas pequeñas o firmas encima, y entonces el campo
  o la firma se reportan como «no se pudo revisar» (advertencia), nunca como error del alumno.
- Texto escrito **a mano** no se lee (Tesseract no reconoce manuscrita); ese caso requiere revisión manual o, en una fase
  posterior, un modelo de visión.
- Con el mismo documento base, un solo dato equivocado puede producir varias observaciones (una por cada documento que
  difiere). Es intencional, pero se puede agrupar más adelante.
