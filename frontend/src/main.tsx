import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import './index.css'
import grained from './grained.js'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
)

const grainEl = document.createElement('div')
grainEl.id = 'grain-overlay'
document.body.appendChild(grainEl)
grained('#grain-overlay', {
  animate: true,
  patternWidth: 200,
  patternHeight: 200,
  grainOpacity: 0.06,
  grainDensity: 1,
  grainWidth: 1,
  grainHeight: 1,
  grainChaos: 0.5,
  grainSpeed: 20,
})
