function formatDateLabel(dateStr: string): string {
  const date = new Date(dateStr)
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const yesterday = new Date(today.getTime() - 86400000)
  const target = new Date(date.getFullYear(), date.getMonth(), date.getDate())

  if (target.getTime() === today.getTime()) return 'Today'
  if (target.getTime() === yesterday.getTime()) return 'Yesterday'

  return date.toLocaleDateString('en-US', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    year: date.getFullYear() !== now.getFullYear() ? 'numeric' : undefined,
  })
}

export default function DateSeparator({ date }: { date: string }) {
  const lineStyle: React.CSSProperties = {
    flex: 1,
    height: '1px',
    background: 'var(--separator-color, #e5e5e5)',
    border: 'none',
    margin: 0,
    padding: 0,
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'row', alignItems: 'center', width: '100%', padding: '4px 0 4px', marginTop: '12px' }}>
      <div style={lineStyle} />
      <span style={{ flexShrink: 0, padding: '0 16px', fontSize: '0.72rem', fontWeight: 500, color: 'var(--text-muted, #a3a3a3)', textTransform: 'uppercase', letterSpacing: '0.1em', whiteSpace: 'nowrap' }}>
        {formatDateLabel(date)}
      </span>
      <div style={lineStyle} />
    </div>
  )
}
