import asyncio
import hashlib
import json
import logging
import os
import re
import secrets
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, Depends, Cookie, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from web_parser import fetch_site_items, parse_feed, discover_feed_url, _fetch_url, fetch_article_description

logger = logging.getLogger("server")

DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "data"))
DB_PATH = os.path.join(DATA_DIR, "boardrss.db")
UPLOADS_DIR = os.path.join(DATA_DIR, "uploads")
STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
os.makedirs(UPLOADS_DIR, exist_ok=True)
DEFAULT_MAX_DB_SIZE_BYTES = 100 * 1024 * 1024
DEFAULT_FETCH_INTERVAL = 2 * 60
USER_AGENT = "BoardRSS/1.0"


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


INIT_SQL = """
CREATE TABLE IF NOT EXISTS sources (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    url         TEXT NOT NULL UNIQUE,
    feed_url    TEXT,
    tags        TEXT DEFAULT '[]',
    enabled     INTEGER DEFAULT 1,
    created_at  TEXT DEFAULT (datetime('now')),
    last_fetched TEXT
);
CREATE TABLE IF NOT EXISTS items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id    INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    guid         TEXT NOT NULL,
    title        TEXT NOT NULL,
    description  TEXT DEFAULT '',
    url          TEXT DEFAULT '',
    tags         TEXT DEFAULT '[]',
    published_at TEXT NOT NULL,
    fetched_at   TEXT DEFAULT (datetime('now')),
    UNIQUE(source_id, guid)
);
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_items_published ON items(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_items_source ON items(source_id);
"""


def init_db():
    conn = get_db()
    conn.executescript(INIT_SQL)
    conn.close()


def db_size_bytes() -> int:
    total = 0
    for suffix in ("", "-wal", "-shm"):
        p = DB_PATH + suffix
        if os.path.exists(p):
            total += os.path.getsize(p)
    return total


def get_max_db_size() -> int:
    val = get_setting("max_db_size_mb", "100")
    try:
        return int(val) * 1024 * 1024
    except ValueError:
        return DEFAULT_MAX_DB_SIZE_BYTES


def enforce_size_limit():
    limit = get_max_db_size()
    conn = get_db()
    max_loops = 20
    while max_loops > 0 and db_size_bytes() > limit:
        max_loops -= 1
        deleted = conn.execute(
            "DELETE FROM items WHERE id IN (SELECT id FROM items ORDER BY published_at ASC LIMIT 500)"
        ).rowcount
        conn.commit()
        if deleted == 0:
            break
    conn.close()


def get_setting(key: str, default: str = "") -> str:
    conn = get_db()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key: str, value: str):
    conn = get_db()
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = ?",
        (key, value, value),
    )
    conn.commit()
    conn.close()


def _hash_password(password: str) -> str:
    salt = get_setting("password_salt")
    if not salt:
        salt = secrets.token_hex(16)
        set_setting("password_salt", salt)
    return hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()


def is_setup_done() -> bool:
    return bool(get_setting("password_hash"))


def is_dashboard_public() -> bool:
    return get_setting("dashboard_public", "true") == "true"


_sessions: dict[str, float] = {}
SESSION_MAX_AGE = 86400


def create_session() -> str:
    token = secrets.token_urlsafe(32)
    _sessions[token] = datetime.now(timezone.utc).timestamp()
    return token


def verify_session(token: str | None) -> bool:
    if token is None or token not in _sessions:
        return False
    created = _sessions[token]
    if datetime.now(timezone.utc).timestamp() - created > SESSION_MAX_AGE:
        _sessions.pop(token, None)
        return False
    return True


async def require_admin(request: Request):
    token = request.cookies.get("session") or request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not verify_session(token):
        raise HTTPException(401, "Not authenticated")


async def fetch_source(source: dict):
    source_id = source["id"]
    url = source["url"]
    feed_url = source["feed_url"]
    source_tags = json.loads(source["tags"]) if source["tags"] else []

    items_parsed = []
    discovered_feed = None

    if feed_url:
        content = await _fetch_url(feed_url)
        if content:
            items_parsed = await parse_feed(content, feed_url, limit=50)

    if not items_parsed:
        items_parsed, discovered_feed = await fetch_site_items(url, limit=50)

        if discovered_feed and discovered_feed != feed_url:
            conn = get_db()
            conn.execute("UPDATE sources SET feed_url = ? WHERE id = ?", (discovered_feed, source_id))
            conn.commit()
            conn.close()

    if items_parsed:
        conn = get_db()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=10, hours=12)).isoformat()
        existing_titles = set()
        existing_map = {}
        for row in conn.execute("SELECT id, title, description FROM items WHERE source_id = ?", (source_id,)).fetchall():
            tn = re.sub(r"[^a-z0-9]", "", row["title"].lower())
            existing_titles.add(tn)
            existing_map[tn] = (row["id"], row["description"] or "")
        for item in items_parsed:
            pub = (item.published_at or datetime.now(timezone.utc)).isoformat()
            if pub < cutoff:
                continue
            title_norm = re.sub(r"[^a-z0-9]", "", (item.title or "").lower())
            dup_key = next((et for et in existing_titles if len(et) > 20 and (title_norm in et or et in title_norm)), None)
            desc = item.description or ""
            desc = re.sub(r"\s*The post\s+.+\s+appeared first on\s+.+\.\s*$", "", desc).strip()
            title_norm = re.sub(r"[^a-z0-9]", "", (item.title or "").lower())
            desc_norm = re.sub(r"[^a-z0-9]", "", desc.lower())
            is_dup = not desc_norm or desc_norm == title_norm or (len(desc_norm) < len(title_norm) * 2 and (desc_norm in title_norm or title_norm in desc_norm))
            if is_dup:
                desc = ""
                try:
                    fetched = await fetch_article_description(item.url)
                    if fetched:
                        desc = fetched
                except Exception:
                    pass
            if len(desc) > 300:
                desc = desc[:297] + "..."
            if dup_key:
                old_id, old_desc = existing_map[dup_key]
                if desc and not old_desc:
                    conn.execute("UPDATE items SET description = ? WHERE id = ?", (desc, old_id))
                continue
            hashtags = set()
            for text in (item.title or "", desc):
                hashtags.update(re.findall(r"#(\w+)", text))
            merged_tags = list(dict.fromkeys(source_tags + [h for h in hashtags if h not in source_tags]))
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO items (source_id, guid, title, description, url, tags, published_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (source_id, item.guid, item.title, desc, item.url, json.dumps(merged_tags), pub),
                )
                existing_titles.add(title_norm)
            except Exception:
                pass
        conn.execute("UPDATE sources SET last_fetched = datetime('now') WHERE id = ?", (source_id,))
        conn.commit()
        conn.close()

    enforce_size_limit()


def get_fetch_interval() -> int:
    val = get_setting("fetch_interval_seconds", str(DEFAULT_FETCH_INTERVAL))
    try:
        return max(30, int(val))
    except ValueError:
        return DEFAULT_FETCH_INTERVAL


async def fetch_all_sources():
    while True:
        try:
            conn = get_db()
            sources = conn.execute("SELECT * FROM sources WHERE enabled = 1").fetchall()
            conn.close()
            tasks = [fetch_source(dict(s)) for s in sources]
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
        except Exception:
            pass
        await asyncio.sleep(get_fetch_interval())


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    task = asyncio.create_task(fetch_all_sources())
    yield
    task.cancel()

app = FastAPI(title="BoardRSS API", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SourceCreate(BaseModel):
    name: str
    url: str
    feed_url: Optional[str] = None
    tags: list[str] = []

class SourceUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    feed_url: Optional[str] = None
    tags: Optional[list[str]] = None
    enabled: Optional[bool] = None

class SetupBody(BaseModel):
    password: str

class LoginBody(BaseModel):
    password: str

class SettingsUpdate(BaseModel):
    dashboard_public: Optional[bool] = None
    password: Optional[str] = None
    dashboard_name: Optional[str] = None
    max_db_size_mb: Optional[int] = None
    fetch_interval_seconds: Optional[int] = None
    theme: Optional[dict] = None
    custom_font_name: Optional[str] = None


@app.get("/api/auth/status")
def auth_status(request: Request):
    token = request.cookies.get("session") or request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    return {
        "setup_done": is_setup_done(),
        "logged_in": verify_session(token),
        "dashboard_public": is_dashboard_public(),
    }


@app.post("/api/auth/setup")
def setup(body: SetupBody):
    if is_setup_done():
        raise HTTPException(400, "Already set up")
    if len(body.password) < 4:
        raise HTTPException(400, "Password must be at least 4 characters")
    set_setting("password_hash", _hash_password(body.password))
    set_setting("dashboard_public", "true")
    token = create_session()
    resp = JSONResponse({"status": "ok"})
    resp.set_cookie("session", token, httponly=True, samesite="lax", max_age=86400 * 30)
    return resp


@app.post("/api/auth/login")
def login(body: LoginBody):
    if not is_setup_done():
        raise HTTPException(400, "Setup not complete")
    if _hash_password(body.password) != get_setting("password_hash"):
        raise HTTPException(401, "Wrong password")
    token = create_session()
    resp = JSONResponse({"status": "ok"})
    resp.set_cookie("session", token, httponly=True, samesite="lax", max_age=86400 * 30)
    return resp


@app.post("/api/auth/logout")
def logout(request: Request):
    token = request.cookies.get("session")
    if token:
        _sessions.pop(token, None)
    resp = JSONResponse({"status": "ok"})
    resp.delete_cookie("session")
    return resp


@app.get("/api/admin/settings", dependencies=[Depends(require_admin)])
def get_settings():
    theme_raw = get_setting("theme")
    theme = json.loads(theme_raw) if theme_raw else None
    return {
        "dashboard_public": is_dashboard_public(),
        "dashboard_name": get_setting("dashboard_name", "BoardRSS"),
        "dashboard_logo": get_setting("dashboard_logo", ""),
        "max_db_size_mb": int(get_setting("max_db_size_mb", "100")),
        "fetch_interval_seconds": get_fetch_interval(),
        "theme": theme,
        "custom_font_name": get_setting("custom_font_name", ""),
    }


@app.put("/api/admin/settings", dependencies=[Depends(require_admin)])
def update_settings(body: SettingsUpdate):
    if body.dashboard_public is not None:
        set_setting("dashboard_public", "true" if body.dashboard_public else "false")
    if body.password is not None:
        if len(body.password) < 4:
            raise HTTPException(400, "Password must be at least 4 characters")
        set_setting("password_hash", _hash_password(body.password))
    if body.dashboard_name is not None:
        set_setting("dashboard_name", body.dashboard_name[:100])
    if body.max_db_size_mb is not None:
        if body.max_db_size_mb < 10:
            raise HTTPException(400, "Minimum size limit is 10 MB")
        set_setting("max_db_size_mb", str(body.max_db_size_mb))
    if body.fetch_interval_seconds is not None:
        if body.fetch_interval_seconds < 30:
            raise HTTPException(400, "Minimum interval is 30 seconds")
        set_setting("fetch_interval_seconds", str(body.fetch_interval_seconds))
    if body.theme is not None:
        set_setting("theme", json.dumps(body.theme))
    if body.custom_font_name is not None:
        set_setting("custom_font_name", body.custom_font_name)
    return {"status": "updated"}


@app.get("/api/admin/sources", dependencies=[Depends(require_admin)])
def list_sources():
    conn = get_db()
    rows = conn.execute("SELECT * FROM sources ORDER BY created_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/admin/sources", dependencies=[Depends(require_admin)])
async def create_source(body: SourceCreate):
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO sources (name, url, feed_url, tags) VALUES (?, ?, ?, ?)",
            (body.name, body.url, body.feed_url, json.dumps(body.tags)),
        )
        conn.commit()
        source_id = cur.lastrowid
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(400, "Source URL already exists")
    conn.close()

    conn = get_db()
    source = dict(conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone())
    conn.close()
    asyncio.create_task(fetch_source(source))
    return {"id": source_id, "status": "created"}


@app.put("/api/admin/sources/{source_id}", dependencies=[Depends(require_admin)])
def update_source(source_id: int, body: SourceUpdate):
    conn = get_db()
    source = conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
    if not source:
        conn.close()
        raise HTTPException(404, "Source not found")

    updates = []
    params = []
    if body.name is not None:
        updates.append("name = ?")
        params.append(body.name)
    if body.url is not None:
        updates.append("url = ?")
        params.append(body.url)
    if body.feed_url is not None:
        updates.append("feed_url = ?")
        params.append(body.feed_url)
    if body.tags is not None:
        updates.append("tags = ?")
        params.append(json.dumps(body.tags))
    if body.enabled is not None:
        updates.append("enabled = ?")
        params.append(1 if body.enabled else 0)

    if updates:
        params.append(source_id)
        conn.execute(f"UPDATE sources SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()

    if body.tags is not None:
        new_source_tags = body.tags
        items = conn.execute(
            "SELECT id, title, description FROM items WHERE source_id = ?",
            (source_id,),
        ).fetchall()
        for item in items:
            hashtags = set()
            for text in (item["title"] or "", item["description"] or ""):
                hashtags.update(re.findall(r"#(\w+)", text))
            merged = list(dict.fromkeys(new_source_tags + [h for h in hashtags if h not in new_source_tags]))
            conn.execute(
                "UPDATE items SET tags = ?, fetched_at = datetime('now') WHERE id = ?",
                (json.dumps(merged), item["id"]),
            )
        conn.commit()

    conn.close()
    return {"status": "updated"}


@app.delete("/api/admin/sources/{source_id}", dependencies=[Depends(require_admin)])
def delete_source(source_id: int):
    conn = get_db()
    conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted"}


@app.post("/api/admin/sources/{source_id}/fetch", dependencies=[Depends(require_admin)])
async def trigger_fetch(source_id: int):
    conn = get_db()
    source = conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
    conn.close()
    if not source:
        raise HTTPException(404, "Source not found")
    asyncio.create_task(fetch_source(dict(source)))
    return {"status": "fetch_started"}


@app.delete("/api/admin/items", dependencies=[Depends(require_admin)])
def reset_feed():
    conn = get_db()
    conn.execute("DELETE FROM items")
    conn.commit()
    conn.execute("VACUUM")
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()
    return {"status": "deleted"}


@app.get("/api/items")
def get_items(request: Request, limit: int = 200, offset: int = 0, source_id: Optional[int] = None):
    if not is_dashboard_public():
        token = request.cookies.get("session") or request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        if not verify_session(token):
            raise HTTPException(401, "Dashboard is private")
    conn = get_db()
    if source_id:
        rows = conn.execute(
            "SELECT i.*, s.name as source_name FROM items i JOIN sources s ON i.source_id = s.id WHERE i.source_id = ? ORDER BY i.published_at DESC LIMIT ? OFFSET ?",
            (source_id, limit, offset),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT i.*, s.name as source_name FROM items i JOIN sources s ON i.source_id = s.id ORDER BY i.published_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/items/since/{timestamp}")
def get_items_since(request: Request, timestamp: str):
    if not is_dashboard_public():
        token = request.cookies.get("session") or request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
        if not verify_session(token):
            raise HTTPException(401, "Dashboard is private")
    conn = get_db()
    rows = conn.execute(
        "SELECT i.*, s.name as source_name FROM items i JOIN sources s ON i.source_id = s.id WHERE i.fetched_at > ? ORDER BY i.published_at DESC LIMIT 100",
        (timestamp,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/stats", dependencies=[Depends(require_admin)])
def get_stats():
    conn = get_db()
    item_count = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    source_count = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
    conn.close()
    max_mb = int(get_setting("max_db_size_mb", "100"))
    return {
        "items": item_count,
        "sources": source_count,
        "db_size_mb": round(db_size_bytes() / (1024 * 1024), 2),
        "max_size_mb": max_mb,
    }


@app.get("/api/customization")
def get_customization():
    theme_raw = get_setting("theme")
    theme = json.loads(theme_raw) if theme_raw else None
    return {
        "dashboard_name": get_setting("dashboard_name", "BoardRSS"),
        "dashboard_logo": get_setting("dashboard_logo", ""),
        "theme": theme,
        "custom_font_name": get_setting("custom_font_name", ""),
        "custom_font_file": get_setting("custom_font_file", ""),
    }


ALLOWED_IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico"}
ALLOWED_FONT_TYPES = {".ttf", ".otf", ".woff", ".woff2"}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024


def _safe_delete_upload(filename: str):
    if not filename:
        return
    safe = os.path.basename(filename)
    path = os.path.join(UPLOADS_DIR, safe)
    if os.path.exists(path) and os.path.commonpath([UPLOADS_DIR, os.path.realpath(path)]) == UPLOADS_DIR:
        os.remove(path)


def _strip_exif(data: bytes, ext: str) -> bytes:
    if ext in {".svg", ".ico"}:
        return data
    try:
        from io import BytesIO
        from PIL import Image
        img = Image.open(BytesIO(data))
        clean = BytesIO()
        img.save(clean, format=img.format or ext.lstrip(".").upper())
        return clean.getvalue()
    except Exception:
        return data


@app.post("/api/admin/upload/logo", dependencies=[Depends(require_admin)])
async def upload_logo(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(400, f"Invalid image type. Allowed: {', '.join(ALLOWED_IMAGE_TYPES)}")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "File too large (max 5 MB)")
    _safe_delete_upload(get_setting("dashboard_logo"))
    fname = f"{secrets.token_hex(8)}{ext}"
    data = _strip_exif(data, ext)
    with open(os.path.join(UPLOADS_DIR, fname), "wb") as f:
        f.write(data)
    set_setting("dashboard_logo", fname)
    return {"status": "uploaded", "filename": fname}


@app.delete("/api/admin/upload/logo", dependencies=[Depends(require_admin)])
def delete_logo():
    _safe_delete_upload(get_setting("dashboard_logo"))
    set_setting("dashboard_logo", "")
    return {"status": "deleted"}


@app.post("/api/admin/upload/font", dependencies=[Depends(require_admin)])
async def upload_font(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_FONT_TYPES:
        raise HTTPException(400, f"Invalid font type. Allowed: {', '.join(ALLOWED_FONT_TYPES)}")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(400, "File too large (max 5 MB)")
    _safe_delete_upload(get_setting("custom_font_file"))
    fname = f"{secrets.token_hex(8)}{ext}"
    with open(os.path.join(UPLOADS_DIR, fname), "wb") as f:
        f.write(data)
    set_setting("custom_font_file", fname)
    font_name = os.path.splitext(file.filename or "font")[0].replace('_', ' ').replace('-', ' ')
    set_setting("custom_font_name", font_name)
    return {"status": "uploaded", "filename": fname, "font_name": font_name}


@app.delete("/api/admin/upload/font", dependencies=[Depends(require_admin)])
def delete_font():
    _safe_delete_upload(get_setting("custom_font_file"))
    set_setting("custom_font_file", "")
    set_setting("custom_font_name", "")
    return {"status": "deleted"}


app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")


@app.get("/api/admin/sources/export", dependencies=[Depends(require_admin)])
def export_sources():
    conn = get_db()
    rows = conn.execute("SELECT name, url, feed_url, tags, enabled FROM sources ORDER BY created_at").fetchall()
    conn.close()
    sources = []
    for r in rows:
        sources.append({
            "name": r["name"],
            "url": r["url"],
            "feed_url": r["feed_url"],
            "tags": json.loads(r["tags"]) if r["tags"] else [],
            "enabled": bool(r["enabled"]),
        })
    return Response(
        content=json.dumps({"version": 1, "sources": sources}, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=boardrss-sources.json"},
    )


class ImportSources(BaseModel):
    version: int = 1
    sources: list[dict]


@app.post("/api/admin/sources/import", dependencies=[Depends(require_admin)])
async def import_sources(file: UploadFile = File(...)):
    data = await file.read()
    if len(data) > 2 * 1024 * 1024:
        raise HTTPException(400, "File too large")
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid JSON")
    sources = payload.get("sources", [])
    if not isinstance(sources, list):
        raise HTTPException(400, "Invalid format: expected 'sources' array")

    imported = 0
    skipped = 0
    conn = get_db()
    for src in sources:
        name = src.get("name", "").strip()
        url = src.get("url", "").strip()
        if not name or not url:
            skipped += 1
            continue
        feed_url = src.get("feed_url") or None
        tags = src.get("tags", [])
        enabled = 1 if src.get("enabled", True) else 0
        try:
            conn.execute(
                "INSERT INTO sources (name, url, feed_url, tags, enabled) VALUES (?, ?, ?, ?, ?)",
                (name, url, feed_url, json.dumps(tags) if isinstance(tags, list) else "[]", enabled),
            )
            imported += 1
        except sqlite3.IntegrityError:
            skipped += 1
    conn.commit()
    conn.close()
    return {"imported": imported, "skipped": skipped}


if os.path.isdir(STATIC_DIR):
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file_path = os.path.join(STATIC_DIR, full_path)
        if full_path and os.path.isfile(file_path):
            return FileResponse(file_path)
        index = os.path.join(STATIC_DIR, "index.html")
        if os.path.isfile(index):
            return FileResponse(index)
        raise HTTPException(404)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
