import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Loader } from '@react-three/drei'
import './index.css'
import App from './App.tsx'
import { ErrorBoundary } from './components/system/ErrorBoundary.tsx'
import { DescargaDesktop } from './components/landing/DescargaDesktop.tsx'
import { esElectron } from './lib/isElectron.ts'

// Axiscam es una app de escritorio, no un sitio web - este mismo build de
// apps/web se sigue publicando en Vercel, pero solo como el punto de
// descarga. Dentro de la ventana de Electron (apps/desktop) se renderiza la
// app real de siempre; en cualquier navegador normal se muestra la landing
// de descarga en su lugar, sin disparar ninguna de las llamadas a la API
// que <App /> hace de entrada (no hay backend que contactar ahi).
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {esElectron() ? (
      <ErrorBoundary>
        <App />
        <Loader />
      </ErrorBoundary>
    ) : (
      <DescargaDesktop />
    )}
  </StrictMode>,
)
