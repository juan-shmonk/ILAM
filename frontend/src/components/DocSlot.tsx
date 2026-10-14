import { useRef } from 'react'
import { CLASE_ESTADO, ETIQUETA_ESTADO, tamano } from '../format'
import type { DocumentoInfo, SeccionDocumento, TipoDocumento } from '../types'

interface Props {
  tipo: TipoDocumento
  documento?: DocumentoInfo
  seccion?: SeccionDocumento
  subiendo: boolean
  deshabilitado: boolean
  onArchivo: (archivo: File) => void
}

export default function DocSlot({ tipo, documento, seccion, subiendo, deshabilitado, onArchivo }: Props) {
  const input = useRef<HTMLInputElement>(null)
  const observaciones = seccion?.hallazgos.filter((h) => h.severidad === 'ERROR' || h.severidad === 'ADVERTENCIA').length ?? 0

  return (
    <div className={`tarjeta doc ${documento ? 'cargado' : ''}`}>
      <div className="doc-cabecera">
        <strong>{tipo.nombre}</strong>
        {seccion && <span className={`insignia ${CLASE_ESTADO[seccion.estado]}`}>{ETIQUETA_ESTADO[seccion.estado]}</span>}
      </div>
      <p className="suave">{tipo.descripcion}</p>

      {documento ? (
        <div className="doc-archivo">
          <a href={`/api/documentos/${documento.id}/archivo`} target="_blank" rel="noreferrer">{documento.archivo}</a>
          <span className="suave">
            versión {documento.version} · {tamano(documento.tamano)}
            {seccion && observaciones > 0 ? ` · ${observaciones} observación(es)` : ''}
          </span>
        </div>
      ) : (
        <p className="suave">Sin subir</p>
      )}

      <input
        ref={input}
        type="file"
        accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
        hidden
        onChange={(e) => {
          const archivo = e.target.files?.[0]
          if (archivo) onArchivo(archivo)
          e.target.value = '' // permite volver a elegir el mismo archivo
        }}
      />
      <button className={documento ? 'btn secundario' : 'btn'} disabled={subiendo || deshabilitado} onClick={() => input.current?.click()}>
        {subiendo ? 'Analizando…' : documento ? 'Reemplazar documento' : 'Subir documento'}
      </button>
    </div>
  )
}
