import type { Estado, Severidad } from './types'

export const ETIQUETA_ESTADO: Record<Estado, string> = {
  SIN_OBSERVACIONES: 'Sin observaciones',
  REQUIERE_CORRECCION: 'Requiere corrección',
  REVISION_MANUAL: 'Revisión manual',
  SIN_DOCUMENTOS: 'Sin documentos',
}

export const CLASE_ESTADO: Record<Estado, string> = {
  SIN_OBSERVACIONES: 'ok',
  REQUIERE_CORRECCION: 'error',
  REVISION_MANUAL: 'aviso',
  SIN_DOCUMENTOS: 'neutro',
}

export const ICONO_SEVERIDAD: Record<Severidad, string> = {
  ERROR: '✕',
  ADVERTENCIA: '⚠',
  INFO: 'ℹ',
  OK: '✓',
}

export function fecha(iso: string): string {
  return new Date(iso).toLocaleString('es-MX', { dateStyle: 'medium', timeStyle: 'short' })
}

export function tamano(bytes: number): string {
  return bytes > 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`
}
