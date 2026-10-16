# Guía para crear documentos de prueba (para el equipo)

Objetivo: tener expedientes **inventados** pero realistas, con errores puestos a propósito y la respuesta correcta
anotada, para medir qué tan bien funciona el sistema. **Nunca uses datos reales de personas.**

Ya existen 16 escenarios automáticos en `backend/samples` (`python -m scripts.generar_muestras`). Lo que aporta el
equipo es **variedad y realismo**: documentos hechos en Word, con otro estilo, fotografiados, escaneados, etc.

## 1. Estructura de cada expediente

```
mis_muestras/
└── 21_mi_caso/
    ├── solicitud.pdf
    ├── plan_trabajo.pdf
    └── ground_truth.json
```

Se evalúa con `python -m scripts.evaluar --muestras mis_muestras`.

## 2. Qué debe tener cada documento

Cada dato va en **una línea con la forma `Etiqueta: valor`**. Las etiquetas aceptadas están en
`backend/app/config_docs/*.json` (por ejemplo «Nombre del alumno», «Matrícula», «Institución receptora»).

| Documento | Título (debe aparecer) | Campos | Firmas |
|---|---|---|---|
| Solicitud | SOLICITUD DE SERVICIO SOCIAL | Nombre del alumno, Matrícula, Carrera, Institución receptora, Fecha de inicio, Fecha de término, Total de horas | Firma del alumno |
| Plan de trabajo | PLAN DE TRABAJO | los anteriores + Responsable, Actividades (lista numerada) | Firma del alumno y Firma del responsable |

**Firmas:** dibuja una línea y escribe debajo el texto exacto «Firma del alumno» / «Firma del responsable». El espacio
**encima** de la línea es donde se firma. Para simular una firma faltante, deja ese espacio vacío.

Fechas válidas: `15/02/2027`, `15-02-2027` o `15 de febrero de 2027`.

> Si el formato oficial real es distinto, no cambies el sistema: cambia las etiquetas en el JSON de configuración.

## 3. Tipos de archivo a producir

Haz de cada caso, cuando puedas, varias versiones: PDF exportado desde Word (texto digital), PDF escaneado, foto con el
celular (recta, torcida, con poca luz) y una versión borrosa. Así se mide el OCR de verdad. (Fotos y escaneos requieren
Tesseract instalado.)

## 4. `ground_truth.json`

```json
{
  "escenario": "21_mi_caso",
  "descripcion": "El plan de trabajo tiene la fecha de inicio distinta.",
  "documentos": {
    "solicitud": "solicitud.pdf",
    "plan_trabajo": "plan_trabajo.pdf"
  },
  "errores_esperados": ["fecha_inicio"],
  "estado_esperado": "REQUIERE_CORRECCION",
  "requiere_ocr": false,
  "campos_escritos": {
    "solicitud": { "nombre": "Ana Ruiz", "matricula": "21530001", "fecha_inicio": "2027-02-15" }
  }
}
```

- `errores_esperados`: lista de **claves de error** (tabla siguiente). Vacía si el expediente está perfecto.
- `estado_esperado`: `SIN_OBSERVACIONES`, `REQUIERE_CORRECCION` o `REVISION_MANUAL` (documento ilegible).
- `requiere_ocr`: `true` si algún archivo es foto o escaneo.
- `campos_escritos` (opcional): lo que de verdad dice cada documento; sirve para medir la exactitud de la extracción.
  Fechas en `AAAA-MM-DD`, horas como número, actividades como lista.

### Claves de error

| Qué inyectaste | Clave |
|---|---|
| Un dato distinto entre documentos, o mal escrito en uno | el nombre del campo: `nombre`, `matricula`, `carrera`, `institucion`, `responsable`, `fecha_inicio`, `fecha_fin`, `horas` |
| Un campo obligatorio vacío | el nombre del campo |
| Firma faltante | `firma:alumno@solicitud`, `firma:responsable@plan_trabajo`, … |
| Documento equivocado (subes la solicitud como plan) | `R005@plan_trabajo` |
| Páginas de más o de menos | `R007@solicitud` |
| Documento ilegible | `R008@solicitud` |

## 5. Casos que conviene cubrir (checklist)

- [ ] Expediente perfecto (varios, con estilos distintos, para medir **falsos positivos**).
- [ ] Cada dato distinto en un solo documento (nombre, matrícula, carrera, institución, fechas, horas).
- [ ] Nombre con pequeñas variaciones (sin acento, apellido faltante, segundo nombre abreviado).
- [ ] Fecha de término anterior a la de inicio; duración menor a 6 meses.
- [ ] Horas distintas de 480 (o de lo que exija el reglamento real).
- [ ] Cada firma ausente, una a la vez y todas juntas.
- [ ] Campos vacíos, uno por documento.
- [ ] Documento cargado en el tipo equivocado; páginas sobrantes.
- [ ] Fotos: nítidas, torcidas, oscuras, borrosas.
- [ ] Al menos 30 expedientes en total antes de sacar conclusiones sobre precisión y recall.

## 6. Cómo leer el resultado de `evaluar`

- **Falso positivo:** el sistema marcó algo que no era error (molesta al alumno).
- **Falso negativo:** había un error y el sistema no lo vio (deja pasar el problema). Suele ser lo más grave.
- Si tus expedientes «perfectos» generan falsos positivos, probablemente el formato de tus documentos no coincide con
  las etiquetas del JSON de configuración: ajústalas o cuéntanos qué formato usaste.
