import { useRef, useState, useCallback, useEffect } from 'react'

interface Props {
  src: string
  onCrop: (blob: Blob) => void
  onCancel: () => void
}

export default function ImageCropper({ src, onCrop, onCancel }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [img, setImg] = useState<HTMLImageElement | null>(null)
  const [scale, setScale] = useState(1)
  const [offset, setOffset] = useState({ x: 0, y: 0 })
  const [dragging, setDragging] = useState(false)
  const dragStart = useRef({ x: 0, y: 0, ox: 0, oy: 0 })

  const CROP_SIZE = 200

  useEffect(() => {
    const image = new Image()
    image.onload = () => {
      setImg(image)
      const minScale = CROP_SIZE / Math.min(image.width, image.height)
      const initScale = Math.max(minScale, CROP_SIZE / Math.max(image.width, image.height))
      setScale(initScale)
      setOffset({
        x: (CROP_SIZE - image.width * initScale) / 2,
        y: (CROP_SIZE - image.height * initScale) / 2,
      })
    }
    image.src = src
  }, [src])

  const draw = useCallback(() => {
    const ctx = canvasRef.current?.getContext('2d')
    if (!ctx || !img) return
    ctx.clearRect(0, 0, CROP_SIZE, CROP_SIZE)
    ctx.drawImage(img, offset.x, offset.y, img.width * scale, img.height * scale)
  }, [img, scale, offset])

  useEffect(() => { draw() }, [draw])

  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault()
    if (!img) return
    const minScale = CROP_SIZE / Math.min(img.width, img.height)
    const newScale = Math.max(minScale, Math.min(scale * (1 - e.deltaY * 0.001), 10))
    const cx = CROP_SIZE / 2
    const cy = CROP_SIZE / 2
    const newOx = cx - (cx - offset.x) * (newScale / scale)
    const newOy = cy - (cy - offset.y) * (newScale / scale)
    setScale(newScale)
    setOffset(clampOffset(newOx, newOy, img, newScale))
  }

  const clampOffset = (ox: number, oy: number, image: HTMLImageElement, s: number) => {
    const w = image.width * s
    const h = image.height * s
    return {
      x: Math.min(0, Math.max(CROP_SIZE - w, ox)),
      y: Math.min(0, Math.max(CROP_SIZE - h, oy)),
    }
  }

  const onPointerDown = (e: React.PointerEvent) => {
    setDragging(true)
    dragStart.current = { x: e.clientX, y: e.clientY, ox: offset.x, oy: offset.y }
    ;(e.target as HTMLElement).setPointerCapture(e.pointerId)
  }

  const onPointerMove = (e: React.PointerEvent) => {
    if (!dragging || !img) return
    const dx = e.clientX - dragStart.current.x
    const dy = e.clientY - dragStart.current.y
    setOffset(clampOffset(dragStart.current.ox + dx, dragStart.current.oy + dy, img, scale))
  }

  const onPointerUp = () => setDragging(false)

  const handleCrop = () => {
    if (!img) return
    const out = document.createElement('canvas')
    out.width = CROP_SIZE
    out.height = CROP_SIZE
    const ctx = out.getContext('2d')!
    ctx.drawImage(img, offset.x, offset.y, img.width * scale, img.height * scale)
    out.toBlob((b) => { if (b) onCrop(b) }, 'image/png')
  }

  return (
    <div className="ic-overlay" onClick={onCancel}>
      <div className="ic-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="ic-title">Crop Logo</div>
        <div className="ic-canvas-wrap" ref={containerRef}>
          <canvas
            ref={canvasRef}
            width={CROP_SIZE}
            height={CROP_SIZE}
            className="ic-canvas"
            onWheel={handleWheel}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
          />
        </div>
        <div className="ic-hint">Drag to pan, scroll to zoom</div>
        <div className="ic-actions">
          <button className="admin-btn admin-btn-ghost" onClick={onCancel}>Cancel</button>
          <button className="admin-btn admin-btn-primary" onClick={handleCrop}>Apply</button>
        </div>
      </div>
    </div>
  )
}
