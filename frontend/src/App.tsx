import { useEffect, useState } from 'react'
import { Link, Navigate, Route, Routes, useNavigate } from 'react-router-dom'
import { api } from './api'
import type { Salud, Usuario } from './types'
import Login from './pages/Login'
import Expedientes from './pages/Expedientes'
import Expediente from './pages/Expediente'

export default function App() {
  const [usuario, setUsuario] = useState<Usuario | null>(null)
  const [cargando, setCargando] = useState(true)
  const [salud, setSalud] = useState<Salud | null>(null)
  const navegar = useNavigate()

  useEffect(() => {
    api.yo().then(setUsuario).catch(() => setUsuario(null)).finally(() => setCargando(false))
    api.salud().then(setSalud).catch(() => setSalud(null))
  }, [])

  async function salir() {
    await api.logout()
    setUsuario(null)
    navegar('/login')
  }

  if (cargando) return <p className="centro">Cargando…</p>

  return (
    <>
      <header className="barra">
        <Link to="/" className="marca">
          <span className="logo">✓</span> Prevalidador documental
        </Link>
        {usuario && (
          <div className="usuario">
            <span>{usuario.nombre}</span>
            <button className="btn secundario" onClick={salir}>Salir</button>
          </div>
        )}
      </header>
      {salud && !salud.ocr_disponible && (
        <div className="franja">
          OCR no instalado: por ahora solo se leen PDF con texto digital (no fotos ni escaneos).
        </div>
      )}
      <main className="contenedor">
        <Routes>
          <Route path="/login" element={usuario ? <Navigate to="/" /> : <Login onEntrar={setUsuario} />} />
          <Route path="/" element={usuario ? <Expedientes /> : <Navigate to="/login" />} />
          <Route path="/expedientes/:id" element={usuario ? <Expediente /> : <Navigate to="/login" />} />
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </main>
    </>
  )
}
