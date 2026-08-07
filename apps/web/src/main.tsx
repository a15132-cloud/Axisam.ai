import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Loader } from '@react-three/drei'
import './index.css'
import App from './App.tsx'
import { ErrorBoundary } from './components/system/ErrorBoundary.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <App />
      <Loader />
    </ErrorBoundary>
  </StrictMode>,
)
