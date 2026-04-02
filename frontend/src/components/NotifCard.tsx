import { motion } from 'framer-motion'
import type { FeedItem } from '../api'

function parseTags(raw: string): string[] {
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

const junkPattern = /(?:Article URL|Comments URL):\s*https?:\/\/\S+|Points:\s*\d+|#\s*Comments:\s*\d+/gi

function cleanDescription(desc: string): string {
  let cleaned = desc.replace(junkPattern, '').replace(/\s*The post\s+.+\s+appeared first on\s+.+\.\s*$/, '').replace(/\s{2,}/g, ' ').trim()
  if (!cleaned || cleaned.length < 10) return ''
  cleaned = cleaned.replace(/\s*(?:\[\.\.\.\]|\[\.{0,3}\]?|\{?\.{2,}|[[{(]\s*)$/, '').replace(/[\s,;:\-]+$/, '')
  return cleaned
}

const cardVariants = {
  hidden: { opacity: 0, y: 20, filter: 'blur(4px)' },
  visible: {
    opacity: 1,
    y: 0,
    filter: 'blur(0px)',
    transition: {
      duration: 0.35,
      ease: 'easeOut' as const,
    },
  },
  exit: {
    opacity: 0,
    filter: 'blur(4px)',
    transition: { duration: 0.2 },
  },
}

export default function NotifCard({ item, activeTags, onTagClick }: { item: FeedItem; activeTags?: string[]; onTagClick?: (tag: string) => void }) {
  const tags = parseTags(item.tags)
  const sourceTags = item.source_name ? [item.source_name, ...tags] : tags
  const rawDesc = item.description ? cleanDescription(item.description) : ''
  const titleNorm = item.title.toLowerCase().replace(/[^a-z0-9]/g, '')
  const descNorm = rawDesc.toLowerCase().replace(/[^a-z0-9]/g, '')
  const isDup = !descNorm || descNorm === titleNorm || (descNorm.length < titleNorm.length * 2 && (titleNorm.includes(descNorm) || descNorm.includes(titleNorm)))
  const desc = isDup ? '' : rawDesc

  const inner = (
    <>
      {item.source_name && (
        <div className="notif-source">{item.source_name}</div>
      )}
      <div className="notif-title">{item.title}</div>
      {desc && (
        <div className="notif-desc">{desc}</div>
      )}
      {sourceTags.length > 0 && (
        <div className="notif-tags">
          {sourceTags.map((tag, i) => (
            <span
              className={`notif-tag${activeTags?.includes(tag) ? ' notif-tag-active' : ''}`}
              key={i}
              onClick={(e) => { e.preventDefault(); e.stopPropagation(); onTagClick?.(tag) }}
              style={{ cursor: 'pointer' }}
            >
              #{tag}
            </span>
          ))}
        </div>
      )}
    </>
  )

  return (
    <motion.div
      className="notif-card"
      variants={cardVariants}
      initial="hidden"
      animate="visible"
      exit="exit"
    >
      {item.url ? (
        <a href={item.url} target="_blank" rel="noopener noreferrer">
          {inner}
        </a>
      ) : (
        inner
      )}
    </motion.div>
  )
}
