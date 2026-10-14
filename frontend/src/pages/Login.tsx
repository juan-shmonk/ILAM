import { FormEvent, useState } from 'react'
import { api } from '../api'
import type { Usuario } from '../types'

export default function Login({ onEntrar }: { onEntrar: (u: Usuario) => void }) {
  const [modo, setModo] = useState<'login' | 'registro'>('login')
  const [nombre, setNombre] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [enviando, setEnviando] = useState(false)

  async function enviar(e: FormEvent) {
    e.preventDefault()
    setError('')
    setEnviando(true)
    try {
      const u = modo === 'login' ? await api.login(email, password) : await api.registro(email, password, nombre)
      onEntrar(u)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error desconocido')
    } finally {
      setEnviando(false)
    }
  }

  return (
    <div className="tarjeta angosta">
      <h1>{modo === 'login' ? 'Iniciar sesión' : 'Crear cuenta'}</h1>
      <p className="suave">
        Revisa tus documentos de servicio social antes de entregarlos. Esta herramienta no sustituye la revisión
        oficial de la institución.
      </p>
      <form onSubmit={enviar} className="formulario">
        {modo === 'registro' && (
          <label>
            Nombre completo
            <input value={nombre} onChange={(e) => setNombre(e.target.value)} required minLength={2} autoComplete="name" />
          </label>
        )}
        <label>
          Correo electrónico
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoComplete="email" />
        </label>
        <label>
          Contraseña
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={modo === 'registro' ? 8 : 1}
            autoComplete={modo === 'login' ? 'current-password' : 'new-password'}
          />
          {modo === 'registro' && <small className="suave">Mínimo 8 caracteres.</small>}
        </label>
        {error && <p className="error-texto" role="alert">{error}</p>}
        <button className="btn" disabled={enviando}>
          {enviando ? 'Enviando…' : modo === 'login' ? 'Entrar' : 'Crear cuenta'}
        </button>
      </form>
      <p className="suave centro-texto">
        {modo === 'login' ? '¿No tienes cuenta? ' : '¿Ya tienes cuenta? '}
        <button className="enlace" onClick={() => setModo(modo === 'login' ? 'registro' : 'login')}>
          {modo === 'login' ? 'Regístrate' : 'Inicia sesión'}
        </button>
      </p>
    </div>
  )
}
