# Catálogo de reglas

Cada regla devuelve un **hallazgo** con: qué requisito se evaluó, la severidad, un mensaje, la **acción** que debe
realizar el alumno, el documento y página donde se encontró, y los valores encontrado/esperado.

Severidades: `ERROR` · `ADVERTENCIA` · `INFO` (no cambia el estado) · `OK`.

Estado del expediente (`estado_de` en `rules/modelos.py`):

1. Algún `ERROR` → **REQUIERE_CORRECCION**
2. Si no, alguna R008 no cumplida (documento no legible) → **REVISION_MANUAL**
3. Si no, alguna `ADVERTENCIA` → **REQUIERE_CORRECCION**
4. Si no → **SIN_OBSERVACIONES** («sujeto a revisión oficial»)

## Reglas por documento (`rules/documento.py`)

| ID | Regla | Severidad | Detalle |
|---|---|---|---|
| R008 | Documento legible | ADVERTENCIA | **Compuerta**: si falla, no se evalúa nada más de ese documento ni participa en comparaciones |
| R005 | Formato esperado | ERROR | El título del documento debe corresponder al tipo elegido; si parece otro tipo lo dice. Si falla, se omiten las reglas de contenido |
| R007 | Páginas completas | ERROR | Rango de páginas por tipo (`config_docs/<tipo>.json → paginas`) |
| R001 | Nombre presente | ERROR | |
| R010 | Campos obligatorios | ERROR | Uno por cada campo obligatorio vacío o ausente |
| R011 | Matrícula válida | ERROR | Expresión regular `matricula_regex` de `requisitos.json` |
| R012 | Fechas legibles | ERROR | Acepta `15/02/2027`, `15-02-2027`, `2027-02-15`, `15 de febrero de 2027` |
| R013 | Periodo coherente | ERROR / ADVERTENCIA | Fin posterior a inicio (error); duración dentro de `duracion_meses` (advertencia) |
| R004 | Horas válidas | ERROR | Debe coincidir con `horas_requeridas` |
| R006 | Firma detectable | ADVERTENCIA | Presencia de tinta sobre la etiqueta «Firma del …». No valida autenticidad |

## Reglas entre documentos (`rules/cruzadas.py`)

Se comparan contra el **documento base** de cada campo (`requisitos.json → fuente_base`). Solo participan documentos
legibles y del formato correcto.

| ID | Campo | Comparación | Base |
|---|---|---|---|
| R015 | Nombre del alumno | difusa* | solicitud |
| R002 | Matrícula | exacta | solicitud |
| R016 | Carrera | difusa* | solicitud |
| R003 | Fecha de inicio | exacta | carta de aceptación |
| R017 | Fecha de término | exacta | carta de aceptación |
| R018 | Institución receptora | difusa* | carta de aceptación |
| R019 | Total de horas | exacta | plan de trabajo |
| R020 | Responsable | difusa* | carta de aceptación |
| R014 | Expediente completo | INFO | faltan documentos / documento excluido |

\* Difusa: tras quitar acentos, mayúsculas, títulos (Lic., Ing.) y ordenar palabras, una coincidencia total es OK;
una similitud ≥ 80 % (nombres) o ≥ 75 % (texto) es **ADVERTENCIA** («se escribe distinto»); menos es **ERROR**.
Umbrales en `requisitos.json → umbrales`.

## Cómo agregar una regla

1. Escribe una función `def rXXX(ctx: ContextoDoc) -> list[Hallazgo]` en `rules/documento.py`.
2. Añádela a `REGLAS_CONTENIDO`.
3. Agrega su prueba en `tests/` (o un escenario en `scripts/generar_muestras.py`).

Para una comparación entre documentos, añade una tupla a `COMPARACIONES` en `rules/cruzadas.py`.
