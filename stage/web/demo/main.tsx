// The demo entry: the real app on a stand-in server (fake.ts). Imported first, so the stand-in is in place before the app starts.
import './fake'

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '../src/index.css'
import App from '../src/App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
