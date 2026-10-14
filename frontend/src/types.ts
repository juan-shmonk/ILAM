export type Severidad = 'ERROR' | 'ADVERTENCIA' | 'INFO' | 'OK'
export type Estado = 'SIN_OBSERVACIONES' | 'REQUIERE_CORRECCION' | 'REVISION_MANUAL' | 'SIN_DOCUMENTOS'

export interface Usuario {
  id: number
  email: string
  nombre: string
  rol: string
}

export interface Hallazgo {
  regla: string
  severidad: Severidad
  titulo: string
  mensaje: string
  accion: string
  documento: string | null
  documentos: string[]
  campo: string | null
  pagina: number | null
  encontrado: unknown
  esperado: unknown
}

export interface SeccionDocumento {
  documento_id: number
  tipo: string
  nombre: string
  version: number | null
  archivo: string | null
  estado: Estado
  calidad: { metodo: string; n_paginas: number; legible: boolean; confianza_ocr: number | null; motivo: string | null }
  hallazgos: Hallazgo[]
}

export type Valor = string | number | string[] | null

export interface FilaComparacion {
  campo: string
  etiqueta: string
  valores: Record<string, Valor>
  consistente: boolean
}

export interface Reporte {
  estado: Estado
  resumen: string
  siguiente_paso: string
  conteos: { errores: number; advertencias: number; correctos: number; info: number }
  completitud: { presentes: string[]; faltantes: string[] }
  documentos: SeccionDocumento[]
  cruzados: Hallazgo[]
  comparacion: FilaComparacion[]
  expediente_json: unknown
  aviso: string
  version_motor: string
  version_requisitos: string
  generado_en: string
}

export interface DocumentoInfo {
  id: number
  tipo: string
  version: number
  archivo: string
  mime: string
  tamano: number
  creado_en: string
}

export interface TipoDocumento {
  codigo: string
  nombre: string
  descripcion: string
  campos: { clave: string; obligatorio: boolean }[]
  firmas: string[]
}

export interface ExpedienteResumen {
  id: number
  tramite: string
  creado_en: string
  documentos: number
  estado: Estado
}

export interface ExpedienteDetalle {
  id: number
  tramite: string
  creado_en: string
  documentos: DocumentoInfo[]
  reporte: Reporte | null
}

export interface Salud {
  estado: string
  ocr_disponible: boolean
  ocr_idioma: string | null
}
