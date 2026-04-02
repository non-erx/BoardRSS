import { useEffect, useRef, useState, useCallback, useMemo } from 'react'
import { AnimatePresence } from 'framer-motion'
import { fetchItems, fetchItemsSince } from '../api'
import type { FeedItem, Customization } from '../api'
import NotifCard from '../components/NotifCard'
import DateSeparator from '../components/DateSeparator'
import SkeletonCards from '../components/SkeletonCards'

const PAGE_SIZE = 15
const LOAD_MORE = 3

function dateKey(dateStr: string): string {
  const d = new Date(dateStr)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export default function Dashboard({ customization }: { customization: Customization | null }) {
  const [allItems, setAllItems] = useState<FeedItem[]>([])
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE)
  const [loading, setLoading] = useState(true)
  const [hasMore, setHasMore] = useState(true)
  const [filterTags, setFilterTags] = useState<string[]>([])
  const lastFetchRef = useRef<string>('')
  const sentinelRef = useRef<HTMLDivElement>(null)

  const loadItems = useCallback(async () => {
    try {
      const data = await fetchItems(300)
      setAllItems(data)
      setHasMore(data.length > PAGE_SIZE)
      if (data.length > 0) {
        lastFetchRef.current = data[0].fetched_at
      }
    } catch {
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadItems()

    const interval = setInterval(async () => {
      if (!lastFetchRef.current) return
      try {
        const newItems = await fetchItemsSince(lastFetchRef.current)
        if (newItems.length > 0) {
          let freshCount = 0
          setAllItems((prev) => {
            const existingIds = new Set(prev.map((i) => i.id))
            const fresh = newItems.filter((i) => !existingIds.has(i.id))
            freshCount = fresh.length
            const updatedIds = new Set(newItems.filter((i) => existingIds.has(i.id)).map((i) => i.id))
            const updatedMap = new Map(newItems.map((i) => [i.id, i]))
            const merged = prev.map((i) => updatedMap.get(i.id) ?? i)
            if (fresh.length === 0 && updatedIds.size === 0) return prev
            if (newItems.length > 0) lastFetchRef.current = newItems[0].fetched_at
            return [...fresh, ...merged].sort((a, b) =>
              new Date(b.published_at).getTime() - new Date(a.published_at).getTime()
            )
          })
          if (freshCount > 0) setVisibleCount((v) => v + freshCount)
        }
      } catch {
      }
    }, 30_000)

    return () => clearInterval(interval)
  }, [loadItems])

  const allTags = useMemo(() => {
    const tagSet = new Set<string>()
    for (const item of allItems) {
      if (item.source_name) tagSet.add(item.source_name)
      try {
        const tags: string[] = JSON.parse(item.tags)
        for (const t of tags) tagSet.add(t)
      } catch {}
    }
    return Array.from(tagSet).sort((a, b) => a.localeCompare(b))
  }, [allItems])

  const filtered = filterTags.length > 0
    ? allItems.filter((item) => {
        try {
          const tags: string[] = JSON.parse(item.tags)
          const lower = filterTags.map((t) => t.toLowerCase())
          return tags.some((t) => lower.includes(t.toLowerCase())) ||
            lower.includes(item.source_name?.toLowerCase() ?? '')
        } catch {
          return false
        }
      })
    : allItems
  const items = filtered.slice(0, visibleCount)

  const onTagClick = useCallback((tag: string) => {
    setFilterTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag]
    )
    setVisibleCount(PAGE_SIZE)
  }, [])

  useEffect(() => {
    const sentinel = sentinelRef.current
    if (!sentinel) return

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          setVisibleCount((prev) => {
            const next = prev + LOAD_MORE
            if (next >= filtered.length) setHasMore(false)
            return Math.min(next, filtered.length)
          })
        }
      },
      { rootMargin: '200px' },
    )

    observer.observe(sentinel)
    return () => observer.disconnect()
  }, [filtered.length])

  const groups: Array<{ key: string; date: string; items: FeedItem[] }> = []

  for (const item of items) {
    const dk = dateKey(item.published_at)
    if (groups.length === 0 || groups[groups.length - 1].key !== dk) {
      groups.push({ key: dk, date: item.published_at, items: [] })
    }
    groups[groups.length - 1].items.push(item)
  }

  return (
    <div className="feed-wrapper">
      <div className="feed-container">
        {loading ? (
          <SkeletonCards />
        ) : allItems.length === 0 ? (
          <div className="empty-state">
            <h2>No notifications yet</h2>
            <p>Add sources in the admin panel to get started</p>
          </div>
        ) : (
          <>
            {allTags.length > 0 && (
              <div className="tag-filter-bar">
                {allTags.map((tag) => (
                  <button
                    key={tag}
                    className={`tag-filter-pill${filterTags.includes(tag) ? ' tag-filter-active' : ''}`}
                    onClick={() => onTagClick(tag)}
                  >
                    #{tag}
                  </button>
                ))}
                {filterTags.length > 0 && (
                  <button className="filter-clear" onClick={() => { setFilterTags([]); setVisibleCount(PAGE_SIZE) }}>×</button>
                )}
              </div>
            )}
            {groups.map((group) => (
              <div key={group.key}>
                <DateSeparator date={group.date} />
                <AnimatePresence mode="popLayout">
                  {group.items.map((item) => (
                    <NotifCard key={item.id} item={item} activeTags={filterTags} onTagClick={onTagClick} />
                  ))}
                </AnimatePresence>
              </div>
            ))}
            {hasMore && <div ref={sentinelRef} style={{ height: 1 }} />}
          </>
        )}
      </div>
    </div>
  )
}
