import type {
  ExpedienteDetalle, ExpedienteResumen, Reporte, Salud, TipoDocumento, Usuario,
} from './types'

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function pedir<T>(url: string, init: RequestInit = {}): Promise<T> {
  const resp = await fetch(url, { credentials: 'include', ...init })
  if (resp.status === 204) return undefined as T
  let cuerpo: unknown = null
  try {
    cuerpo = await resp.json()
  } catch {
    /* sin cuerpo JSON */
  }
  if (!resp.ok) {
    const detalle = (cuerpo as { detail?: unknown } | null)?.detail
    const mensaje = typeof detalle === 'string' ? detalle : 'Ocurrió un error. Intenta de nuevo.'
    throw new ApiError(mensaje, resp.status)
  }
  return cuerpo as T
}

const json = (datos: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(datos),
})

export const api = {
  salud: () => pedir<Salud>('/api/salud'),
  yo: () => pedir<Usuario>('/api/auth/yo'),
  registro: (email: string, password: string, nombre: string) =>
    pedir<Usuario>('/api/auth/registro', json({ email, password, nombre })),
  login: (email: string, password: string) => pedir<Usuario>('/api/auth/login', json({ email, password })),
  logout: () => pedir<void>('/api/auth/logout', { method: 'POST' }),
  tiposDocumento: () => pedir<TipoDocumento[]>('/api/tipos-documento'),
  expedientes: () => pedir<ExpedienteResumen[]>('/api/expedientes'),
  crearExpediente: () => pedir<{ id: number }>('/api/expedientes', { method: 'POST' }),
  expediente: (id: number) => pedir<ExpedienteDetalle>(`/api/expedientes/${id}`),
  revalidar: (id: number) => pedir<Reporte>(`/api/expedientes/${id}/revalidar`, { method: 'POST' }),
  subirDocumento: (id: number, tipo: string, archivo: File) => {
    const datos = new FormData()
    datos.append('tipo', tipo)
    datos.append('archivo', archivo)
    return pedir<{ reporte: Reporte }>(`/api/expedientes/${id}/documentos`, { method: 'POST', body: datos })
  },
}
