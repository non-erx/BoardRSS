const API = '/api'

export interface Source {
  id: number
  name: string
  url: string
  feed_url: string | null
  tags: string
  enabled: number
  created_at: string
  last_fetched: string | null
}

export interface FeedItem {
  id: number
  source_id: number
  guid: string
  title: string
  description: string
  url: string
  tags: string
  published_at: string
  fetched_at: string
  source_name: string
}

export interface Stats {
  items: number
  sources: number
  db_size_mb: number
  max_size_mb: number
}

export interface AuthStatus {
  setup_done: boolean
  logged_in: boolean
  dashboard_public: boolean
}

export interface AdminSettings {
  dashboard_public: boolean
  dashboard_name: string
  dashboard_logo: string
  max_db_size_mb: number
  fetch_interval_seconds: number
  theme: ThemeColors | null
  custom_font_name: string
}

export interface ThemeColors {
  bg?: string
  card_bg?: string
  border?: string
  text_primary?: string
  text_secondary?: string
  text_muted?: string
  tag_bg?: string
  tag_text?: string
  accent?: string
  separator_color?: string
}

export interface Customization {
  dashboard_name: string
  dashboard_logo: string
  theme: ThemeColors | null
  custom_font_name: string
  custom_font_file: string
}

export async function getAuthStatus(): Promise<AuthStatus> {
  const res = await fetch(`${API}/auth/status`)
  if (!res.ok) throw new Error('Failed to get auth status')
  return res.json()
}

export async function setup(password: string): Promise<void> {
  const res = await fetch(`${API}/auth/setup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Setup failed')
  }
}

export async function login(password: string): Promise<void> {
  const res = await fetch(`${API}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Login failed')
  }
}

export async function logout(): Promise<void> {
  await fetch(`${API}/auth/logout`, { method: 'POST' })
}

export async function getAdminSettings(): Promise<AdminSettings> {
  const res = await fetch(`${API}/admin/settings`)
  if (!res.ok) throw new Error('Failed to get settings')
  return res.json()
}

export async function updateAdminSettings(
  data: Partial<{
    dashboard_public: boolean
    password: string
    dashboard_name: string
    max_db_size_mb: number
    fetch_interval_seconds: number
    theme: ThemeColors
    custom_font_name: string
  }>,
): Promise<void> {
  const res = await fetch(`${API}/admin/settings`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to update settings')
  }
}

export async function fetchItems(limit = 200, offset = 0): Promise<FeedItem[]> {
  const res = await fetch(`${API}/items?limit=${limit}&offset=${offset}`)
  if (!res.ok) throw new Error('Failed to fetch items')
  return res.json()
}

export async function fetchItemsSince(timestamp: string): Promise<FeedItem[]> {
  const res = await fetch(`${API}/items/since/${encodeURIComponent(timestamp)}`)
  if (!res.ok) throw new Error('Failed to fetch new items')
  return res.json()
}

export async function fetchSources(): Promise<Source[]> {
  const res = await fetch(`${API}/admin/sources`)
  if (!res.ok) throw new Error('Failed to fetch sources')
  return res.json()
}

export async function createSource(data: {
  name: string
  url: string
  feed_url?: string
  tags?: string[]
}): Promise<{ id: number; status: string }> {
  const res = await fetch(`${API}/admin/sources`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to create source')
  }
  return res.json()
}

export async function updateSource(
  id: number,
  data: Partial<{ name: string; url: string; feed_url: string; tags: string[]; enabled: boolean }>,
): Promise<void> {
  const res = await fetch(`${API}/admin/sources/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error('Failed to update source')
}

export async function deleteSource(id: number): Promise<void> {
  const res = await fetch(`${API}/admin/sources/${id}`, { method: 'DELETE' })
  if (!res.ok) throw new Error('Failed to delete source')
}

export async function triggerFetch(id: number): Promise<void> {
  const res = await fetch(`${API}/admin/sources/${id}/fetch`, { method: 'POST' })
  if (!res.ok) throw new Error('Failed to trigger fetch')
}

export async function resetFeed(): Promise<void> {
  const res = await fetch(`${API}/admin/items`, { method: 'DELETE' })
  if (!res.ok) throw new Error('Failed to reset feed')
}

export async function fetchStats(): Promise<Stats> {
  const res = await fetch(`${API}/stats`)
  if (!res.ok) throw new Error('Failed to fetch stats')
  return res.json()
}

export async function getCustomization(): Promise<Customization> {
  const res = await fetch(`${API}/customization`)
  if (!res.ok) throw new Error('Failed to get customization')
  return res.json()
}

export async function uploadLogo(file: File): Promise<{ filename: string }> {
  const fd = new FormData()
  fd.append('file', file)
  const res = await fetch(`${API}/admin/upload/logo`, { method: 'POST', body: fd })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Upload failed')
  }
  return res.json()
}

export async function deleteLogo(): Promise<void> {
  const res = await fetch(`${API}/admin/upload/logo`, { method: 'DELETE' })
  if (!res.ok) throw new Error('Failed to delete logo')
}

export async function uploadFont(file: File): Promise<{ filename: string; font_name: string }> {
  const fd = new FormData()
  fd.append('file', file)
  const res = await fetch(`${API}/admin/upload/font`, { method: 'POST', body: fd })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Upload failed')
  }
  return res.json()
}

export async function deleteFont(): Promise<void> {
  const res = await fetch(`${API}/admin/upload/font`, { method: 'DELETE' })
  if (!res.ok) throw new Error('Failed to delete font')
}

export async function exportSources(): Promise<void> {
  const res = await fetch(`${API}/admin/sources/export`)
  if (!res.ok) throw new Error('Export failed')
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'boardrss-sources.json'
  a.click()
  URL.revokeObjectURL(url)
}

export async function importSources(file: File): Promise<{ imported: number; skipped: number }> {
  const fd = new FormData()
  fd.append('file', file)
  const res = await fetch(`${API}/admin/sources/import`, { method: 'POST', body: fd })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Import failed')
  }
  return res.json()
}
