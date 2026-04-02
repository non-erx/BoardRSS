import { useEffect, useState, useRef } from 'react'
import { Link } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import ColorPicker from '../components/ColorPicker'
import ImageCropper from '../components/ImageCropper'
import {
  fetchSources,
  createSource,
  deleteSource,
  updateSource,
  triggerFetch,
  fetchStats,
  getAdminSettings,
  updateAdminSettings,
  uploadLogo,
  deleteLogo,
  uploadFont,
  deleteFont,
  exportSources,
  importSources,
  resetFeed,
  logout,
} from '../api'
import type { Source, Stats, AdminSettings, ThemeColors } from '../api'

function parseTags(raw: string): string[] {
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function parseSizeToMB(input: string): number | null {
  const m = input.trim().match(/^([\d.]+)\s*(gb?|mb?|tb?)?$/i)
  if (!m) return null
  const num = parseFloat(m[1])
  if (isNaN(num) || num <= 0) return null
  const unit = (m[2] || 'm').charAt(0).toLowerCase()
  if (unit === 't') return Math.round(num * 1024 * 1024)
  if (unit === 'g') return Math.round(num * 1024)
  return Math.round(num)
}

function formatSize(mb: number): string {
  if (mb >= 1024 * 1024) return `${(mb / (1024 * 1024)).toFixed(mb % (1024 * 1024) === 0 ? 0 : 1)} TB`
  if (mb >= 1024) return `${(mb / 1024).toFixed(mb % 1024 === 0 ? 0 : 1)} GB`
  return `${mb} MB`
}

type Tab = 'sources' | 'settings' | 'theme' | 'data'

export default function Admin({ onLogout }: { onLogout: () => void }) {
  const [tab, setTab] = useState<Tab>('sources')
  const [sources, setSources] = useState<Source[]>([])
  const [stats, setStats] = useState<Stats | null>(null)
  const [settings, setSettings] = useState<AdminSettings | null>(null)
  const [name, setName] = useState('')
  const [url, setUrl] = useState('')
  const [feedUrl, setFeedUrl] = useState('')
  const [tags, setTags] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [pwMsg, setPwMsg] = useState('')

  const [editId, setEditId] = useState<number | null>(null)
  const [editName, setEditName] = useState('')
  const [editUrl, setEditUrl] = useState('')
  const [editFeedUrl, setEditFeedUrl] = useState('')
  const [editTags, setEditTags] = useState('')

  const [dashName, setDashName] = useState('')
  const [sizeInput, setSizeInput] = useState('100 MB')
  const [sizeMsg, setSizeMsg] = useState('')
  const [fetchInterval, setFetchInterval] = useState(120)
  const [fetchIntervalMsg, setFetchIntervalMsg] = useState('')
  const [themeColors, setThemeColors] = useState<ThemeColors>({})
  const [importMsg, setImportMsg] = useState('')
  const [cropSrc, setCropSrc] = useState<string | null>(null)
  const logoInputRef = useRef<HTMLInputElement>(null)
  const fontInputRef = useRef<HTMLInputElement>(null)
  const importInputRef = useRef<HTMLInputElement>(null)

  const DEFAULT_THEME: Required<ThemeColors> = {
    bg: '#fafafa', card_bg: '#ffffff', border: '#e5e5e5',
    text_primary: '#0a0a0a', text_secondary: '#737373', text_muted: '#a3a3a3',
    tag_bg: '#f5f5f5', tag_text: '#525252', accent: '#171717', separator_color: '#e5e5e5',
  }

  const THEME_LABELS: Record<string, string> = {
    bg: 'Background', card_bg: 'Card', border: 'Border',
    text_primary: 'Text', text_secondary: 'Text Secondary', text_muted: 'Text Muted',
    tag_bg: 'Tag Background', tag_text: 'Tag Text', accent: 'Accent', separator_color: 'Separator',
  }

  const reload = async () => {
    try {
      const [s, st, sett] = await Promise.all([fetchSources(), fetchStats(), getAdminSettings()])
      setSources(s); setStats(st); setSettings(sett)
      setDashName(sett.dashboard_name || 'BoardRSS')
      setSizeInput(formatSize(sett.max_db_size_mb || 100))
      setFetchInterval(sett.fetch_interval_seconds || 120)
      setThemeColors(sett.theme || {})
    } catch {
      window.location.href = '/admin'
    }
  }

  useEffect(() => { reload() }, [])

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim() || !url.trim()) return
    setError(''); setSaving(true)
    try {
      await createSource({ name: name.trim(), url: url.trim(), feed_url: feedUrl.trim() || undefined, tags: tags.split(',').map(t => t.trim()).filter(Boolean) })
      setName(''); setUrl(''); setFeedUrl(''); setTags(''); await reload()
    } catch (err: any) { setError(err.message || 'Failed') } finally { setSaving(false) }
  }
  const handleDelete = async (id: number) => { await deleteSource(id); await reload() }
  const handleToggle = async (s: Source) => { await updateSource(s.id, { enabled: !s.enabled }); await reload() }
  const handleFetch = async (id: number) => { await triggerFetch(id) }
  const startEdit = (s: Source) => { setEditId(s.id); setEditName(s.name); setEditUrl(s.url); setEditFeedUrl(s.feed_url || ''); setEditTags(parseTags(s.tags).join(', ')) }
  const cancelEdit = () => setEditId(null)
  const saveEdit = async () => {
    if (editId === null) return
    await updateSource(editId, { name: editName.trim(), url: editUrl.trim(), feed_url: editFeedUrl.trim(), tags: editTags.split(',').map(t => t.trim()).filter(Boolean) })
    setEditId(null); await reload()
  }

  const handleTogglePublic = async () => { if (!settings) return; await updateAdminSettings({ dashboard_public: !settings.dashboard_public }); await reload() }
  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault(); setPwMsg('')
    if (newPassword.length < 4) { setPwMsg('Min 4 characters'); return }
    try { await updateAdminSettings({ password: newPassword }); setNewPassword(''); setPwMsg('Updated') }
    catch (err: any) { setPwMsg(err.message || 'Failed') }
  }
  const handleSaveName = async () => { await updateAdminSettings({ dashboard_name: dashName.trim() || 'BoardRSS' }); await reload() }
  const handleSaveSize = async () => {
    setSizeMsg('')
    const mb = parseSizeToMB(sizeInput)
    if (!mb || mb < 10) { setSizeMsg('Invalid size (min 10 MB)'); return }
    await updateAdminSettings({ max_db_size_mb: mb }); await reload(); setSizeMsg('Saved')
  }
  const handleSaveFetchInterval = async () => {
    setFetchIntervalMsg('')
    if (fetchInterval < 30) { setFetchIntervalMsg('Minimum is 30 seconds'); return }
    await updateAdminSettings({ fetch_interval_seconds: fetchInterval }); await reload(); setFetchIntervalMsg('Saved')
  }
  const handleLogoSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]; if (!f) return
    const url = URL.createObjectURL(f)
    setCropSrc(url)
    e.target.value = ''
  }
  const handleCropDone = async (blob: Blob) => {
    setCropSrc(null)
    const file = new File([blob], 'logo.png', { type: 'image/png' })
    try { await uploadLogo(file); window.location.reload() } catch (err: any) { alert(err.message) }
  }
  const handleCropCancel = () => { setCropSrc(null) }
  const handleDeleteLogo = async () => { await deleteLogo(); window.location.reload() }
  const handleFontUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]; if (!f) return
    try { await uploadFont(f); window.location.reload() } catch (err: any) { alert(err.message) }
    e.target.value = ''
  }
  const handleDeleteFont = async () => { await deleteFont(); window.location.reload() }
  const handleThemeChange = (key: string, value: string) => setThemeColors(prev => ({ ...prev, [key]: value }))
  const handleSaveTheme = async () => {
    const toSave: ThemeColors = {}
    for (const [k, v] of Object.entries(themeColors)) if (v && v !== (DEFAULT_THEME as any)[k]) (toSave as any)[k] = v
    await updateAdminSettings({ theme: Object.keys(toSave).length > 0 ? toSave : {} }); window.location.reload()
  }
  const handleResetTheme = async () => { setThemeColors({}); await updateAdminSettings({ theme: {} }); window.location.reload() }
  const handleExport = async () => { try { await exportSources() } catch (err: any) { alert(err.message) } }
  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]; if (!f) return; setImportMsg('')
    try { const r = await importSources(f); setImportMsg(`Imported ${r.imported}, skipped ${r.skipped}`); await reload() }
    catch (err: any) { setImportMsg(err.message) }
    e.target.value = ''
  }
  const handleResetFeed = async () => {
    if (!confirm('Delete ALL feed items? This cannot be undone.')) return
    await resetFeed(); window.location.reload()
  }
  const handleLogout = async () => { await logout(); onLogout() }

  const navTabs: { key: Tab; label: string }[] = [
    { key: 'sources', label: 'Sources' },
    { key: 'settings', label: 'Settings' },
    { key: 'theme', label: 'Appearance' },
    { key: 'data', label: 'Data' },
  ]

  return (
    <div className="ap">
      <header className="ap-topbar">
        <div className="ap-topbar-inner">
          <nav className="ap-nav">
            {navTabs.map((t) => (
              <button key={t.key} className={`ap-nav-item${tab === t.key ? ' active' : ''}`} onClick={() => setTab(t.key)}>{t.label}</button>
            ))}
          </nav>
          <div className="ap-topbar-right">
            {stats && (
              <span className="ap-stats-mini">{stats.sources} sources &middot; {stats.items} items &middot; {stats.db_size_mb}/{formatSize(stats.max_size_mb)}</span>
            )}
            <Link to="/" className="ap-nav-item" style={{ textDecoration: 'none' }}>← Feed</Link>
            <button className="ap-nav-item" onClick={handleLogout}>Log out</button>
          </div>
        </div>
      </header>

      <main className="ap-main">
        {tab === 'sources' && (
          <>
            <div className="ap-section-header">
              <h2>Sources</h2>
              <span className="ap-section-desc">{sources.length} source{sources.length !== 1 ? 's' : ''}</span>
            </div>
            <form className="admin-form" onSubmit={handleAdd}>
              <h2>Add Source</h2>
              <div className="admin-row">
                <input className="admin-input" placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} required />
                <input className="admin-input" placeholder="URL" type="url" value={url} onChange={(e) => setUrl(e.target.value)} required />
              </div>
              <div className="admin-row">
                <input className="admin-input" placeholder="Feed URL (auto-detected)" value={feedUrl} onChange={(e) => setFeedUrl(e.target.value)} />
                <input className="admin-input" placeholder="Tags, comma separated" value={tags} onChange={(e) => setTags(e.target.value)} />
              </div>
              {error && <div style={{ color: '#dc2626', fontSize: '0.82rem' }}>{error}</div>}
              <button className="admin-btn admin-btn-primary" type="submit" disabled={saving} style={{ alignSelf: 'flex-start' }}>
                {saving ? 'Adding\u2026' : 'Add'}
              </button>
            </form>
            <div className="source-list">
              <AnimatePresence>
                {sources.map((source) => {
                  const sTags = parseTags(source.tags)
                  return (
                    <motion.div key={source.id} className="source-card" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, x: -20 }} transition={{ duration: 0.15 }} layout>
                      {editId === source.id ? (
                        <>
                          <div className="source-info source-edit">
                            <input className="admin-input" value={editName} onChange={e => setEditName(e.target.value)} placeholder="Name" />
                            <input className="admin-input" value={editUrl} onChange={e => setEditUrl(e.target.value)} placeholder="Site URL" />
                            <input className="admin-input" value={editFeedUrl} onChange={e => setEditFeedUrl(e.target.value)} placeholder="Feed URL" />
                            <input className="admin-input" value={editTags} onChange={e => setEditTags(e.target.value)} placeholder="Tags" />
                          </div>
                          <div className="source-actions">
                            <button className="admin-btn admin-btn-primary" onClick={saveEdit}>{'\u2713'}</button>
                            <button className="admin-btn admin-btn-ghost" onClick={cancelEdit}>{'\u2715'}</button>
                          </div>
                        </>
                      ) : (
                        <>
                          <div className="source-info">
                            <div className="source-name">{source.name}</div>
                            <div className="source-url">{source.url}</div>
                            {sTags.length > 0 && <div className="source-tags">{sTags.map((t, i) => <span className="notif-tag" key={i}>#{t}</span>)}</div>}
                            {source.last_fetched && <div className="source-meta">Last fetch: {new Date(source.last_fetched).toLocaleString()}</div>}
                          </div>
                          <div className="source-actions">
                            <button className="admin-btn admin-btn-ghost" onClick={() => startEdit(source)} title="Edit">{'\u270E'}</button>
                            <button className="admin-btn admin-btn-ghost" onClick={() => handleFetch(source.id)} title="Fetch now">{'\u21BB'}</button>
                            <button className={`source-toggle ${source.enabled ? 'enabled' : 'disabled'}`} onClick={() => handleToggle(source)} title={source.enabled ? 'Disable' : 'Enable'} />
                            <button className="admin-btn admin-btn-danger" onClick={() => handleDelete(source.id)}>{'\u00D7'}</button>
                          </div>
                        </>
                      )}
                    </motion.div>
                  )
                })}
              </AnimatePresence>
            </div>
          </>
        )}

        {tab === 'settings' && settings && (
          <>
            <div className="ap-section-header"><h2>Settings</h2></div>
            <div className="admin-form">
              <div className="settings-row" style={{ borderTop: 'none' }}>
                <span className="settings-label">Dashboard Name</span>
                <div style={{ display: 'flex', gap: '8px', alignItems: 'center', marginTop: '4px' }}>
                  <input className="admin-input" value={dashName} onChange={(e) => setDashName(e.target.value)} placeholder="BoardRSS" style={{ maxWidth: '280px' }} />
                  <button className="admin-btn admin-btn-primary" onClick={handleSaveName}>Save</button>
                </div>
              </div>
              <div className="settings-row">
                <span className="settings-label">Logo</span>
                <span className="settings-desc">PNG, SVG, WebP, ICO. Max 5 MB</span>
                <div style={{ display: 'flex', gap: '8px', alignItems: 'center', marginTop: '4px' }}>
                  {settings.dashboard_logo && <img src={`/uploads/${settings.dashboard_logo}`} alt="logo" style={{ height: '32px', objectFit: 'contain', borderRadius: '4px' }} />}
                  <button className="admin-btn admin-btn-ghost" onClick={() => logoInputRef.current?.click()}>{settings.dashboard_logo ? 'Change' : 'Upload'}</button>
                  {settings.dashboard_logo && <button className="admin-btn admin-btn-danger" onClick={handleDeleteLogo}>Remove</button>}
                  <input ref={logoInputRef} type="file" accept="image/*" hidden onChange={handleLogoSelect} />
                </div>
              </div>
              <div className="settings-row">
                <span className="settings-label">Public Dashboard</span>
                <span className="settings-desc">Anyone can view the feed without logging in</span>
                <button className={`source-toggle ${settings.dashboard_public ? 'enabled' : 'disabled'}`} onClick={handleTogglePublic} style={{ marginTop: '4px' }} />
              </div>
              <form className="settings-row" onSubmit={handleChangePassword}>
                <span className="settings-label">Password</span>
                <div style={{ display: 'flex', gap: '8px', alignItems: 'center', marginTop: '4px' }}>
                  <input className="admin-input" type="password" placeholder="New password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} style={{ maxWidth: '200px' }} />
                  <button className="admin-btn admin-btn-primary" type="submit">Update</button>
                </div>
                {pwMsg && <div style={{ fontSize: '0.78rem', color: pwMsg === 'Updated' ? '#16a34a' : '#dc2626', marginTop: '4px' }}>{pwMsg}</div>}
              </form>
              <div className="settings-row">
                <span className="settings-label">Storage Limit</span>
                <span className="settings-desc">e.g. 100MB, 2GB, 500M, 1T</span>
                <div style={{ display: 'flex', gap: '8px', alignItems: 'center', marginTop: '4px' }}>
                  <input className="admin-input" value={sizeInput} onChange={(e) => setSizeInput(e.target.value)} placeholder="100MB" style={{ maxWidth: '160px' }}
                    onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleSaveSize() } }} />
                  <button className="admin-btn admin-btn-primary" onClick={handleSaveSize}>Save</button>
                </div>
                {sizeMsg && <div style={{ fontSize: '0.78rem', color: sizeMsg === 'Saved' ? '#16a34a' : '#dc2626', marginTop: '4px' }}>{sizeMsg}</div>}
              </div>
              <div className="settings-row">
                <span className="settings-label">Scan Interval</span>
                <span className="settings-desc">How often sources are checked for new items (minimum 30s)</span>
                <div style={{ display: 'flex', gap: '8px', alignItems: 'center', marginTop: '4px' }}>
                  <select className="admin-input" value={fetchInterval} onChange={(e) => setFetchInterval(Number(e.target.value))} style={{ maxWidth: '200px' }}>
                    <option value={30}>30 seconds</option>
                    <option value={60}>1 minute</option>
                    <option value={120}>2 minutes</option>
                    <option value={300}>5 minutes</option>
                    <option value={600}>10 minutes</option>
                    <option value={900}>15 minutes</option>
                    <option value={1800}>30 minutes</option>
                    <option value={3600}>1 hour</option>
                  </select>
                  <button className="admin-btn admin-btn-primary" onClick={handleSaveFetchInterval}>Save</button>
                </div>
                {fetchIntervalMsg && <div style={{ fontSize: '0.78rem', color: fetchIntervalMsg === 'Saved' ? '#16a34a' : '#dc2626', marginTop: '4px' }}>{fetchIntervalMsg}</div>}
              </div>
            </div>
          </>
        )}

        {tab === 'theme' && settings && (
          <>
            <div className="ap-section-header"><h2>Appearance</h2></div>
            <div className="admin-form">
              <h2>Colors</h2>
              <div className="theme-grid">
                {Object.entries(DEFAULT_THEME).map(([key, defaultVal]) => (
                  <div key={key} className="theme-swatch-row">
                    <label className="theme-swatch-label">{THEME_LABELS[key] || key}</label>
                    <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                      <ColorPicker value={(themeColors as any)[key] || defaultVal} onChange={(hex) => handleThemeChange(key, hex)} />
                      <span className="theme-hex">{(themeColors as any)[key] || defaultVal}</span>
                    </div>
                  </div>
                ))}
              </div>
              <div style={{ display: 'flex', gap: '8px', marginTop: '8px' }}>
                <button className="admin-btn admin-btn-primary" onClick={handleSaveTheme}>Apply Theme</button>
                <button className="admin-btn admin-btn-ghost" onClick={handleResetTheme}>Reset to Default</button>
              </div>
            </div>
            <div className="admin-form" style={{ marginTop: '16px' }}>
              <h2>Font</h2>
              <span className="settings-desc">Upload a custom font (TTF, OTF, WOFF, WOFF2). Max 5 MB</span>
              <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                {settings.custom_font_name && <span style={{ fontSize: '0.85rem', fontWeight: 500 }}>{settings.custom_font_name}</span>}
                <button className="admin-btn admin-btn-ghost" onClick={() => fontInputRef.current?.click()}>{settings.custom_font_name ? 'Change Font' : 'Upload Font'}</button>
                {settings.custom_font_name && <button className="admin-btn admin-btn-danger" onClick={handleDeleteFont}>Remove</button>}
                <input ref={fontInputRef} type="file" accept=".ttf,.otf,.woff,.woff2" hidden onChange={handleFontUpload} />
              </div>
            </div>
          </>
        )}

        {tab === 'data' && (
          <>
            <div className="ap-section-header"><h2>Data</h2></div>
            <div className="admin-form">
              <h2>Export / Import</h2>
              <span className="settings-desc">Export or import your sources as a JSON file</span>
              <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                <button className="admin-btn admin-btn-primary" onClick={handleExport}>Export Sources</button>
                <button className="admin-btn admin-btn-ghost" onClick={() => importInputRef.current?.click()}>Import Sources</button>
                <input ref={importInputRef} type="file" accept=".json" hidden onChange={handleImport} />
              </div>
              {importMsg && <div style={{ fontSize: '0.78rem', color: 'var(--text-secondary)', marginTop: '4px' }}>{importMsg}</div>}
            </div>
            <div className="admin-form" style={{ marginTop: '16px' }}>
              <h2>Danger Zone</h2>
              <div className="settings-row" style={{ borderTop: 'none' }}>
                <span className="settings-label">Reset Feed</span>
                <span className="settings-desc">Delete all fetched items. Sources will be kept.</span>
                <button className="admin-btn admin-btn-danger" onClick={handleResetFeed} style={{ alignSelf: 'flex-start', marginTop: '4px' }}>Delete All Items</button>
              </div>
            </div>
          </>
        )}
      </main>
      {cropSrc && <ImageCropper src={cropSrc} onCrop={handleCropDone} onCancel={handleCropCancel} />}
    </div>
  )
}
