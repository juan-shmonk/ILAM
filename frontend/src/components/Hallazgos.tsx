import { ICONO_SEVERIDAD } from '../format'
import type { Hallazgo } from '../types'

export type HallazgoConDoc = Hallazgo & { origen: string }

export default function Hallazgos({ items }: { items: HallazgoConDoc[] }) {
  return (
    <ul className="hallazgos">
      {items.map((h, i) => (
        <li key={`${h.regla}-${h.documento}-${h.campo}-${i}`} className={`hallazgo sev-${h.severidad}`}>
          <span className="icono" aria-hidden>{ICONO_SEVERIDAD[h.severidad]}</span>
          <div>
            <div className="hallazgo-titulo">
              <strong>{h.titulo}</strong>
              <span className="origen">
                {h.origen}
                {h.pagina ? ` · pág. ${h.pagina}` : ''}
              </span>
              <span className="regla">{h.regla}</span>
            </div>
            <p>{h.mensaje}</p>
            {h.accion && h.severidad !== 'OK' && <p className="accion">→ {h.accion}</p>}
          </div>
        </li>
      ))}
    </ul>
  )
}
