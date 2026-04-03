# BoardRSS
Self-hosted RSS reader that feels like a notification feed. Add sites and get a clean, scrollable stream - no accounts or third-party services.
Built with FastAPI + React. Runs anywhere Docker works.
---

## Quick Start
**Docker (recommended)**
```bash
docker compose up -d
```
Open `http://localhost:8000`, set admin password, add sources.

**Local dev**
```bash
pip install -r requirements.txt
cd backend && python server.py
cd frontend && npm install && npm run dev
```

Or run both:

```bash
python start.py
```
---

## Features

* Auto **RSS/Atom discovery** (with scraping fallback)
* **Bot bypass** (Cloudflare, etc.)
* **Google News fallback**
* **Tag filtering**
* **Custom UI** (logo, colors, font)
* **Import/export**
* **Auto-cleanup**
* **Adjustable polling**
---

## Admin
`/admin` panel lets you manage sources, trigger fetches, customize UI, and control access.
---

## Stack
* Backend: FastAPI, SQLite
* Frontend: React, TypeScript
* Deploy: Docker
---

## License
MIT License

Copyright (c) [2026] [non-erx]

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
