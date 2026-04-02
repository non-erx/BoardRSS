import { useEffect, useState, useCallback } from 'react'
import { Routes, Route, useLocation } from 'react-router-dom'
import { getAuthStatus, getCustomization } from './api'
import type { AuthStatus, Customization } from './api'
import Dashboard from './pages/Dashboard'
import Admin from './pages/Admin'
import Login from './pages/Login'

const CSS_VAR_MAP: Record<string, string> = {
  bg: '--bg',
  card_bg: '--card-bg',
  border: '--border',
  text_primary: '--text-primary',
  text_secondary: '--text-secondary',
  text_muted: '--text-muted',
  tag_bg: '--tag-bg',
  tag_text: '--tag-text',
  accent: '--accent',
  separator_color: '--separator-color',
}

export default function App() {
  const [auth, setAuth] = useState<AuthStatus | null>(null)
  const [customization, setCustomization] = useState<Customization | null>(null)
  const location = useLocation()

  const checkAuth = useCallback(async () => {
    try {
      const status = await getAuthStatus()
      setAuth(status)
    } catch {
    }
  }, [])

  const loadCustomization = useCallback(async () => {
    try {
      const c = await getCustomization()
      setCustomization(c)
      const root = document.documentElement
      if (c.theme) {
        for (const [key, cssVar] of Object.entries(CSS_VAR_MAP)) {
          const val = (c.theme as any)[key]
          if (val) root.style.setProperty(cssVar, val)
          else root.style.removeProperty(cssVar)
        }
      } else {
        for (const cssVar of Object.values(CSS_VAR_MAP)) {
          root.style.removeProperty(cssVar)
        }
      }
      let styleEl = document.getElementById('custom-font-style') as HTMLStyleElement | null
      if (c.custom_font_name && c.custom_font_file) {
        const safeName = c.custom_font_name.replace(/[^a-zA-Z0-9 _-]/g, '')
        const safeFile = c.custom_font_file.replace(/[^a-zA-Z0-9._-]/g, '')
        if (safeName && safeFile) {
          if (!styleEl) {
            styleEl = document.createElement('style')
            styleEl.id = 'custom-font-style'
            document.head.appendChild(styleEl)
          }
          styleEl.textContent = `
            @font-face {
              font-family: '${safeName}';
              src: url('/uploads/${safeFile}');
              font-display: swap;
            }
          `
          root.style.setProperty('--font', `'${safeName}', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif`)
        }
      } else {
        if (styleEl) styleEl.textContent = ''
        root.style.removeProperty('--font')
      }
      document.title = c.dashboard_name || 'BoardRSS'
      let favicon = document.querySelector('link[rel="icon"]') as HTMLLinkElement | null
      if (c.dashboard_logo) {
        if (!favicon) {
          favicon = document.createElement('link')
          favicon.rel = 'icon'
          document.head.appendChild(favicon)
        }
        favicon.href = `/uploads/${c.dashboard_logo}`
      } else if (favicon) {
        favicon.href = 'data:,'
      }
    } catch {
    }
  }, [])

  useEffect(() => {
    checkAuth()
    loadCustomization()
  }, [checkAuth, loadCustomization])

  useEffect(() => {
    loadCustomization()
  }, [location.pathname, loadCustomization])

  if (!auth) {
    return null
  }

  const isAdminRoute = location.pathname === '/admin'

  if (!auth.setup_done) {
    if (isAdminRoute) {
      return <Login isSetup onSuccess={checkAuth} />
    }
    return (
      <Routes>
        <Route path="*" element={<Dashboard customization={customization} />} />
      </Routes>
    )
  }

  if (isAdminRoute && !auth.logged_in) {
    return <Login isSetup={false} onSuccess={checkAuth} />
  }

  if (!isAdminRoute && !auth.dashboard_public && !auth.logged_in) {
    return <Login isSetup={false} onSuccess={checkAuth} />
  }

  return (
    <Routes>
      <Route path="/" element={<Dashboard customization={customization} />} />
      <Route path="/admin" element={<Admin onLogout={checkAuth} />} />
    </Routes>
  )
}
