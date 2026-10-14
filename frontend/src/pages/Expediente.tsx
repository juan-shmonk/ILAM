import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api'
import Comparacion from '../components/Comparacion'
import DocSlot from '../components/DocSlot'
import Hallazgos, { HallazgoConDoc } from '../components/Hallazgos'
import { CLASE_ESTADO, ETIQUETA_ESTADO, fecha } from '../format'
import type { ExpedienteDetalle, TipoDocumento } from '../types'

const ORDEN = { ERROR: 0, ADVERTENCIA: 1, INFO: 2, OK: 3 } as const

export default function Expediente() {
  const { id } = useParams()
  const expId = Number(id)
  const [detalle, setDetalle] = useState<ExpedienteDetalle | null>(null)
  const [tipos, setTipos] = useState<TipoDocumento[]>([])
  const [subiendo, setSubiendo] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [copiado, setCopiado] = useState(false)

  const cargar = useCallback(async () => {
    setDetalle(await api.expediente(expId))
  }, [expId])

  useEffect(() => {
    Promise.all([cargar(), api.tiposDocumento().then(setTipos)]).catch((e: Error) => setError(e.message))
  }, [cargar])

  async function subir(tipo: string, archivo: File) {
    setSubiendo(tipo)
    setError('')
    try {
      await api.subirDocumento(expId, tipo, archivo)
      await cargar()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo subir el documento')
    } finally {
      setSubiendo(null)
    }
  }

  if (!detalle) return error ? <p className="error-texto">{error}</p> : <p className="suave">Cargando…</p>

  const reporte = detalle.reporte
  const todos: HallazgoConDoc[] = reporte
    ? [
        ...reporte.documentos.flatMap((d) => d.hallazgos.map((h) => ({ ...h, origen: d.nombre }))),
        ...reporte.cruzados.map((h) => ({ ...h, origen: 'Entre documentos' })),
      ]
    : []
  const observaciones = todos.filter((h) => h.severidad !== 'OK').sort((a, b) => ORDEN[a.severidad] - ORDEN[b.severidad])
  const correctos = todos.filter((h) => h.severidad === 'OK')
  const json = reporte ? JSON.stringify(reporte.expediente_json, null, 2) : ''

  return (
    <>
      <Link to="/" className="volver">← Mis expedientes</Link>
      <div className="fila-titulo">
        <h1>Expediente #{detalle.id}</h1>
        <span className="suave">Servicio social · creado {fecha(detalle.creado_en)}</span>
      </div>

      <h2>1. Sube tus documentos</h2>
      <p className="suave">
        Acepta PDF (mejor con texto digital), PNG o JPG de hasta 15 MB. Puedes reemplazar un documento cuantas veces
        quieras; se conserva el historial.
      </p>
      {error && <p className="error-texto" role="alert">{error}</p>}
      <div className="rejilla-docs">
        {tipos.map((t) => (
          <DocSlot
            key={t.codigo}
            tipo={t}
            documento={detalle.documentos.find((d) => d.tipo === t.codigo)}
            seccion={reporte?.documentos.find((d) => d.tipo === t.codigo)}
            subiendo={subiendo === t.codigo}
            deshabilitado={subiendo !== null}
            onArchivo={(f) => subir(t.codigo, f)}
          />
        ))}
      </div>

      {reporte && reporte.estado !== 'SIN_DOCUMENTOS' && (
        <>
          <h2>2. Resultado de la prevalidación</h2>
          <section className={`banner ${CLASE_ESTADO[reporte.estado]}`}>
            <div className="banner-estado">{ETIQUETA_ESTADO[reporte.estado].toUpperCase()}</div>
            <p><strong>{reporte.resumen}</strong></p>
            <p>{reporte.siguiente_paso}</p>
            <div className="chips">
              <span className="chip error">✕ {reporte.conteos.errores} errores</span>
              <span className="chip aviso">⚠ {reporte.conteos.advertencias} advertencias</span>
              <span className="chip ok">✓ {reporte.conteos.correctos} correctos</span>
            </div>
          </section>

          {observaciones.length > 0 && (
            <>
              <h3>Observaciones</h3>
              <Hallazgos items={observaciones} />
            </>
          )}

          <h3>Comparación entre documentos</h3>
          <Comparacion reporte={reporte} />

          <details className="detalle">
            <summary>Ver lo que salió correcto ({correctos.length})</summary>
            <Hallazgos items={correctos} />
          </details>

          <details className="detalle">
            <summary>Ver el JSON del expediente</summary>
            <p className="suave">
              Datos ya normalizados que usan las reglas para comparar. Fechas en formato AAAA-MM-DD.
            </p>
            <button
              className="btn secundario"
              onClick={() => navigator.clipboard.writeText(json).then(() => { setCopiado(true); setTimeout(() => setCopiado(false), 1500) })}
            >
              {copiado ? 'Copiado ✓' : 'Copiar JSON'}
            </button>
            <pre className="codigo">{json}</pre>
          </details>

          <p className="aviso-legal">{reporte.aviso}</p>
          <p className="suave pequeno">
            Motor v{reporte.version_motor} · requisitos «{reporte.version_requisitos}» (valores de ejemplo por
            confirmar) · generado {fecha(reporte.generado_en)}
          </p>
        </>
      )}
    </>
  )
}
