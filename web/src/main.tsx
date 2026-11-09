import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { registerSW } from 'virtual:pwa-register'
import App from './App'
import './ui/tokens.css'

registerSW({ immediate: true })

// Chiede al browser di non cancellare i dati locali (IndexedDB) quando lo spazio scarseggia.
navigator.storage?.persist?.().catch(() => {})

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>)
