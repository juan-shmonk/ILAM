import type { Reporte, Valor } from '../types'

function mostrar(v: Valor | undefined): string {
  if (v === null || v === undefined || v === '') return '—'
  return Array.isArray(v) ? v.join('; ') : String(v)
}

export default function Comparacion({ reporte }: { reporte: Reporte }) {
  if (reporte.comparacion.length === 0) return null
  return (
    <div className="tabla-scroll">
      <table className="tabla">
        <thead>
          <tr>
            <th>Dato</th>
            {reporte.documentos.map((d) => <th key={d.tipo}>{d.nombre}</th>)}
            <th>Coincide</th>
          </tr>
        </thead>
        <tbody>
          {reporte.comparacion.map((f) => (
            <tr key={f.campo} className={f.consistente ? '' : 'conflicto'}>
              <td>{f.etiqueta}</td>
              {reporte.documentos.map((d) => <td key={d.tipo}>{mostrar(f.valores[d.tipo])}</td>)}
              <td>{f.consistente ? '✓' : '⚠'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
