# BoardRSS

A self-hosted RSS reader that looks and feels like a notification feed. Add your favorite sites, and BoardRSS turns them into a clean, scrollable stream of updates — no account needed to read, no third-party services involved.

Built with FastAPI and React. Runs anywhere Docker does.

---

## Quick Start

### Docker (recommended)

```bash
docker compose up -d
```

Open `http://localhost:8000`, set up your admin password, add some sources — that's it.

All data lives in a single Docker volume (`boardrss-data`).

### Local development

**Backend:**
```bash
pip install -r requirements.txt
cd backend && python server.py
```

**Frontend:**
```bash
cd frontend && npm install && npm run dev
```

The frontend runs on `http://localhost:3000` and proxies API requests to the backend on `:8000`.

Or run both at once:
```bash
python start.py
```

---

## What it does

- **Feed discovery** — Give it any URL. It'll find the RSS/Atom feed automatically. If there isn't one, it falls back to scraping the page directly (HTML, JSON-LD, sitemaps, etc.)
- **Bot detection bypass** — Uses browser-level TLS fingerprinting to get past Cloudflare and similar protections
- **Google News fallback** — When a site blocks scrapers or has too few items, BoardRSS supplements results from Google News RSS
- **Tag filtering** — Filter your feed by tags with a multi-select tag bar at the top
- **Customization** — Change the dashboard name, logo, colors, and font from the admin panel
- **Import/export** — Back up your sources as JSON and restore them anywhere
- **Auto-cleanup** — Set a max database size and old items get pruned automatically
- **Configurable polling** — Set how often sources are checked (default: every 2 minutes)

---

## Admin panel

Go to `/admin` after setup. From there you can:

- Add, edit, enable/disable, or delete RSS sources
- Trigger a manual fetch for any source
- Adjust the polling interval and database size limit
- Upload a custom logo and font
- Set theme colors
- Export/import your source list
- Make the dashboard public or require login to view

---

## Tech stack

| Layer | Tech |
|-------|------|
| Backend | Python, FastAPI, SQLite (WAL mode), feedparser, BeautifulSoup, curl_cffi |
| Frontend | React, TypeScript, Vite, Framer Motion |
| Deployment | Docker (multi-stage build) |

---

## License

MIT
