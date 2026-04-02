import { useState, useRef, useEffect, useCallback } from 'react'

function hsvToHex(h: number, s: number, v: number): string {
  const f = (n: number) => {
    const k = (n + h / 60) % 6
    return v - v * s * Math.max(Math.min(k, 4 - k, 1), 0)
  }
  const toHex = (x: number) => Math.round(x * 255).toString(16).padStart(2, '0')
  return `#${toHex(f(5))}${toHex(f(3))}${toHex(f(1))}`
}

function hexToHsv(hex: string): [number, number, number] {
  const r = parseInt(hex.slice(1, 3), 16) / 255
  const g = parseInt(hex.slice(3, 5), 16) / 255
  const b = parseInt(hex.slice(5, 7), 16) / 255
  const max = Math.max(r, g, b), min = Math.min(r, g, b)
  const d = max - min
  let h = 0
  if (d !== 0) {
    if (max === r) h = 60 * (((g - b) / d) % 6)
    else if (max === g) h = 60 * ((b - r) / d + 2)
    else h = 60 * ((r - g) / d + 4)
  }
  if (h < 0) h += 360
  const s = max === 0 ? 0 : d / max
  return [h, s, max]
}

interface Props {
  value: string
  onChange: (hex: string) => void
}

export default function ColorPicker({ value, onChange }: Props) {
  const [open, setOpen] = useState(false)
  const [hsv, setHsv] = useState<[number, number, number]>(() => hexToHsv(value))
  const [hexInput, setHexInput] = useState(value)
  const wrapRef = useRef<HTMLDivElement>(null)
  const svRef = useRef<HTMLDivElement>(null)
  const hueRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const newHsv = hexToHsv(value)
    setHsv(newHsv)
    setHexInput(value)
  }, [value])

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  const emitColor = useCallback((h: number, s: number, v: number) => {
    const hex = hsvToHex(h, s, v)
    setHsv([h, s, v])
    setHexInput(hex)
    onChange(hex)
  }, [onChange])

  const handleSvMove = useCallback((e: React.MouseEvent | MouseEvent) => {
    const rect = svRef.current?.getBoundingClientRect()
    if (!rect) return
    const s = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width))
    const v = Math.max(0, Math.min(1, 1 - (e.clientY - rect.top) / rect.height))
    emitColor(hsv[0], s, v)
  }, [hsv, emitColor])

  const handleHueMove = useCallback((e: React.MouseEvent | MouseEvent) => {
    const rect = hueRef.current?.getBoundingClientRect()
    if (!rect) return
    const h = Math.max(0, Math.min(359, ((e.clientX - rect.left) / rect.width) * 360))
    emitColor(h, hsv[1], hsv[2])
  }, [hsv, emitColor])

  const makeDrag = (handler: (e: MouseEvent) => void) => (e: React.MouseEvent) => {
    handler(e.nativeEvent)
    const onMove = (ev: MouseEvent) => { ev.preventDefault(); handler(ev) }
    const onUp = () => { window.removeEventListener('mousemove', onMove); window.removeEventListener('mouseup', onUp) }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }

  const handleHexCommit = () => {
    const clean = hexInput.trim()
    if (/^#[0-9a-f]{6}$/i.test(clean)) {
      const newHsv = hexToHsv(clean)
      setHsv(newHsv)
      onChange(clean.toLowerCase())
    } else {
      setHexInput(value)
    }
  }

  const currentHex = hsvToHex(hsv[0], hsv[1], hsv[2])

  return (
    <div className="cp-wrap" ref={wrapRef}>
      <button
        type="button"
        className="cp-swatch"
        style={{ background: currentHex }}
        onClick={() => setOpen(!open)}
      />
      {open && (
        <div className="cp-popover">
          <div
            className="cp-sv"
            ref={svRef}
            style={{ background: `hsl(${hsv[0]}, 100%, 50%)` }}
            onMouseDown={makeDrag(handleSvMove)}
          >
            <div className="cp-sv-white" />
            <div className="cp-sv-black" />
            <div
              className="cp-sv-cursor"
              style={{ left: `${hsv[1] * 100}%`, top: `${(1 - hsv[2]) * 100}%` }}
            />
          </div>
          <div className="cp-hue" ref={hueRef} onMouseDown={makeDrag(handleHueMove)}>
            <div className="cp-hue-cursor" style={{ left: `${(hsv[0] / 360) * 100}%` }} />
          </div>
          <input
            className="cp-hex-input"
            value={hexInput}
            onChange={(e) => setHexInput(e.target.value)}
            onBlur={handleHexCommit}
            onKeyDown={(e) => { if (e.key === 'Enter') handleHexCommit() }}
            spellCheck={false}
          />
        </div>
      )}
    </div>
  )
}
