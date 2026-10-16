import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { CLASE_ESTADO, ETIQUETA_ESTADO, fecha } from '../format'
import type { ExpedienteResumen } from '../types'

export default function Expedientes() {
  const [lista, setLista] = useState<ExpedienteResumen[] | null>(null)
  const [error, setError] = useState('')
  const navegar = useNavigate()

  useEffect(() => {
    api.expedientes().then(setLista).catch((e: Error) => setError(e.message))
  }, [])

  async function nuevo() {
    try {
      const { id } = await api.crearExpediente()
      navegar(`/expedientes/${id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo crear el expediente')
    }
  }

  return (
    <>
      <div className="fila-titulo">
        <h1>Mis expedientes</h1>
        <button className="btn" onClick={nuevo}>+ Nuevo expediente de servicio social</button>
      </div>
      {error && <p className="error-texto">{error}</p>}
      {lista === null && !error && <p className="suave">Cargando…</p>}
      {lista?.length === 0 && (
        <div className="tarjeta vacio">
          <p>Aún no tienes expedientes.</p>
          <p className="suave">Crea uno para subir tu solicitud y tu plan de trabajo.</p>
        </div>
      )}
      <ul className="lista-tarjetas">
        {lista?.map((e) => (
          <li key={e.id}>
            <Link to={`/expedientes/${e.id}`} className="tarjeta enlace-tarjeta">
              <div>
                <strong>Expediente #{e.id}</strong>
                <div className="suave">Creado {fecha(e.creado_en)} · {e.documentos} de 3 documentos</div>
              </div>
              <span className={`insignia ${CLASE_ESTADO[e.estado]}`}>{ETIQUETA_ESTADO[e.estado]}</span>
            </Link>
          </li>
        ))}
      </ul>
    </>
  )
}
