import asyncio
import hashlib
import json as _json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import unescape
from typing import Optional
from urllib.parse import urljoin, urlparse

import feedparser
from curl_cffi import AsyncSession
from bs4 import BeautifulSoup, Tag

logger = logging.getLogger("web_parser")


@dataclass
class ParsedItem:
    title: str
    description: str = ""
    url: str = ""
    published_at: Optional[datetime] = None
    source_title: str = ""
    guid: str = ""

    def __post_init__(self):
        if not self.guid:
            raw = self.url or self.title
            self.guid = hashlib.sha256(raw.encode()).hexdigest()[:32]


_HTTP_SEM = asyncio.Semaphore(30)


async def _fetch_url(url: str, timeout: int = 15) -> Optional[str]:
    async with _HTTP_SEM:
        try:
            async with AsyncSession(impersonate="chrome") as client:
                resp = await client.get(url, timeout=timeout)
                if resp.status_code == 200:
                    return resp.text
        except Exception:
            pass
    return None


async def _fetch_url_with_status(url: str, timeout: int = 15) -> tuple[Optional[str], int]:
    async with _HTTP_SEM:
        try:
            async with AsyncSession(impersonate="chrome") as client:
                resp = await client.get(url, timeout=timeout)
                if resp.status_code == 200:
                    return resp.text, 200
                return None, resp.status_code
        except Exception:
            pass
    return None, 0


async def _try_google_news_rss(site_url: str, limit: int = 50) -> list[ParsedItem]:
    parsed = urlparse(site_url)
    domain = parsed.netloc.removeprefix("www.")
    path_parts = [p for p in parsed.path.strip("/").split("/") if p and len(p) > 2]
    keywords = " ".join(path_parts[-2:]) if path_parts else ""
    q = f"site:{domain} {keywords}".strip()
    gnews_url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
    content = await _fetch_url(gnews_url, timeout=10)
    if not content:
        return []
    items = await parse_feed(content, gnews_url, limit)
    return [i for i in items if not _is_junk_item(i.url, i.title)]


_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "ref", "fbclid", "gclid", "mc_cid", "mc_eid",
}


def _strip_tracking_params(url: str) -> str:
    if not url or "?" not in url:
        return url
    parsed = urlparse(url)
    params = parsed.query.split("&")
    clean = [p for p in params if p.split("=")[0].lower() not in _TRACKING_PARAMS]
    cleaned_query = "&".join(clean)
    return parsed._replace(query=cleaned_query).geturl()


def _clean_html(raw: str) -> str:
    return re.sub(r"<[^>]+>", "", unescape(raw)).strip()


def _clean_description(raw: str) -> str:
    text = _clean_html(raw)
    text = re.sub(r"\s+", " ", text).strip()
    text = text[:1000]
    text = re.sub(r"\s*(?:\[\.\.\.[\]\)]?|\[\.{0,3}\]?|\{?\.{2,}|[\[{(]\s*)$", "", text).rstrip(" ,;:-")
    return text


async def fetch_article_description(url: str, timeout: int = 8) -> str:
    if not url or "news.google.com" in url:
        return ""
    try:
        async with _HTTP_SEM:
            async with AsyncSession(impersonate="chrome") as client:
                resp = await client.get(url, timeout=timeout)
                if resp.status_code != 200:
                    return ""
                html = resp.text
        soup = BeautifulSoup(html[:50000], "html.parser")
        og = soup.find("meta", attrs={"property": "og:description"})
        if og and og.get("content", "").strip():
            return _clean_description(og["content"])
        meta = soup.find("meta", attrs={"name": "description"})
        if meta and meta.get("content", "").strip():
            return _clean_description(meta["content"])
        tw = soup.find("meta", attrs={"name": "twitter:description"})
        if tw and tw.get("content", "").strip():
            return _clean_description(tw["content"])
        ld_scripts = soup.find_all("script", type="application/ld+json")
        for script in ld_scripts[:5]:
            try:
                data = _json.loads(script.string or "")
                nodes = data if isinstance(data, list) else [data]
                for node in nodes:
                    if not isinstance(node, dict):
                        continue
                    desc = node.get("description") or node.get("abstract") or ""
                    if desc:
                        return _clean_description(desc)
            except Exception:
                pass
    except Exception:
        pass
    return ""


_JUNK_TITLE_RE = re.compile(
    r"^(cookie|privacy|terms|login|sign.?in|subscribe|newsletter|404|403)",
    re.I,
)


def _is_junk_item(url: str, title: str) -> bool:
    if _JUNK_TITLE_RE.search(title):
        return True
    p = urlparse(url)
    if p.path in ("/", "") and not p.query:
        return True
    return False


def _abs_url(url: str, base: str) -> str:
    if not url:
        return ""
    if url.startswith(("http://", "https://")):
        return url
    return urljoin(base, url)


def _origin(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def _normalize_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    return f"{parsed.netloc}{path}"


_IMAGE_EXT_RE = re.compile(r"\.(jpe?g|png|gif|webp|avif|bmp|svg|tiff?)(\?.*)?$", re.I)
_BAD_IMAGE_RE = re.compile(
    r"(data:|\.svg(\?|$)|/pixel\.|/spacer\.|/blank\.|1x1|transparent\.|/placeholder\.)", re.I,
)
_LAZY_PLACEHOLDER_RE = re.compile(
    r"(data:image/gif|/lazy\.|/placeholder\.|\.gif(\?|$))", re.I,
)


def _is_valid_image_url(url: str) -> bool:
    if not url or len(url) > 2000:
        return False
    if _BAD_IMAGE_RE.search(url):
        return False
    if _LAZY_PLACEHOLDER_RE.search(url):
        return False
    return True


def _best_srcset_url(srcset: str, page_url: str) -> Optional[str]:
    best_url: Optional[str] = None
    best_w = 0
    for part in srcset.split(","):
        tokens = part.strip().split()
        if not tokens:
            continue
        url = tokens[0]
        w = 0
        if len(tokens) >= 2 and tokens[1].lower().endswith("w"):
            try:
                w = int(tokens[1][:-1])
            except ValueError:
                pass
        if w > best_w:
            best_w = w
            best_url = url
    if best_url:
        return _abs_url(best_url, page_url)
    return None


def _extract_hero_image(html: str, page_url: str) -> Optional[str]:
    soup = BeautifulSoup(html, "html.parser")

    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        candidate = og["content"].strip()
        if _is_valid_image_url(candidate):
            return _abs_url(candidate, page_url)

    tw = (
        soup.find("meta", attrs={"name": "twitter:image"})
        or soup.find("meta", property="twitter:image")
        or soup.find("meta", attrs={"name": "twitter:image:src"})
    )
    if tw and tw.get("content"):
        candidate = tw["content"].strip()
        if _is_valid_image_url(candidate):
            return _abs_url(candidate, page_url)

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = _json.loads(script.string or "")
            nodes = data if isinstance(data, list) else [data]
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                if "@graph" in node:
                    nodes.extend(n for n in node["@graph"] if isinstance(n, dict))
                    continue
                img = node.get("image")
                if isinstance(img, str) and _is_valid_image_url(img):
                    return _abs_url(img, page_url)
                if isinstance(img, dict):
                    src = img.get("url") or img.get("contentUrl")
                    if src and _is_valid_image_url(src):
                        return _abs_url(src, page_url)
                if isinstance(img, list) and img:
                    first = img[0]
                    src = first if isinstance(first, str) else (
                        first.get("url") or first.get("contentUrl") if isinstance(first, dict) else None
                    )
                    if src and _is_valid_image_url(src):
                        return _abs_url(src, page_url)
        except Exception:
            continue

    _SKIP_SRC_RE = re.compile(
        r"(logo|icon|avatar|badge|sprite|pixel|tracking|btn|button|emoji|flag)",
        re.I,
    )
    _LAZY_ATTRS = ("data-src", "data-lazy-src", "data-original", "data-srcset")
    for container in (
        soup.find("article"),
        soup.find("main"),
        soup.find(class_=re.compile(r"article|post|content|entry", re.I)),
        soup,
    ):
        if container is None:
            continue
        for picture in container.find_all("picture"):
            for source_tag in picture.find_all("source"):
                srcset = source_tag.get("srcset", "")
                if srcset:
                    best = _best_srcset_url(srcset, page_url)
                    if best and _is_valid_image_url(best):
                        return best
            img = picture.find("img")
            if img:
                src = img.get("src") or img.get("data-src") or ""
                if src and not src.startswith("data:") and _is_valid_image_url(src):
                    return _abs_url(src, page_url)
        for img in container.find_all("img"):
            src = (img.get("src") or "").strip()
            for attr in _LAZY_ATTRS:
                candidate = (img.get(attr) or "").strip()
                if candidate and not candidate.startswith("data:") and not _LAZY_PLACEHOLDER_RE.search(candidate):
                    src = candidate
                    break
            if not src or src.startswith("data:") or _SKIP_SRC_RE.search(src):
                continue
            if not _is_valid_image_url(src):
                continue
            srcset = img.get("srcset", "") or img.get("data-srcset", "")
            if srcset:
                best = _best_srcset_url(srcset, page_url)
                if best:
                    return best
            else:
                w = img.get("width", "")
                h = img.get("height", "")
                try:
                    if w and int(w) < 100:
                        continue
                    if h and int(h) < 100:
                        continue
                except (ValueError, TypeError):
                    pass
            return _abs_url(src, page_url)

    return None


_FEED_PATHS = [
    "/feed", "/feed.xml", "/rss", "/rss.xml", "/atom.xml",
    "/feed.atom", "/index.xml", "/feeds/posts/default",
    "/blog/feed", "/blog/rss.xml", "/news/feed",
    "/?feed=rss2", "/?format=feed&type=rss",
]


def _parse_feed_date(entry) -> Optional[datetime]:
    for attr in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, attr, None)
        if parsed:
            try:
                return datetime(*parsed[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    for attr in ("published", "updated"):
        raw = getattr(entry, attr, None)
        if raw:
            try:
                return datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except Exception:
                pass
    return None


def _make_guid(entry, source_url: str) -> str:
    raw = getattr(entry, "id", None) or getattr(entry, "link", None) or ""
    if raw:
        return hashlib.sha256(raw.encode()).hexdigest()[:32]
    title = getattr(entry, "title", "") or ""
    return hashlib.sha256(f"{source_url}:{title}".encode()).hexdigest()[:32]


def _parse_feed_sync(content: str, source_url: str, limit: int) -> list[ParsedItem]:
    feed = feedparser.parse(content)
    if not feed.entries:
        return []

    items: list[ParsedItem] = []
    feed_title = getattr(feed.feed, "title", None) or source_url
    for entry in feed.entries[:limit]:
        title = _clean_html(getattr(entry, "title", "") or "")
        if not title:
            continue

        desc_raw = getattr(entry, "summary", "") or getattr(entry, "description", "") or ""
        desc = _clean_description(desc_raw)

        link = _strip_tracking_params(getattr(entry, "link", None) or "")
        pub = _parse_feed_date(entry) or datetime.now(timezone.utc)
        guid = _make_guid(entry, source_url)

        if _is_junk_item(link, title):
            continue

        items.append(ParsedItem(
            title=title,
            description=desc,
            url=link,
            published_at=pub,
            source_title=feed_title,
            guid=guid,
        ))

    return items


async def parse_feed(content: str, source_url: str, limit: int = 50) -> list[ParsedItem]:
    return await asyncio.to_thread(_parse_feed_sync, content, source_url, limit)


def _discover_feed_link_from_html(html: str, base_url: str) -> Optional[str]:
    soup = BeautifulSoup(html, "html.parser")
    for link in soup.find_all("link", rel="alternate"):
        mime = (link.get("type") or "").lower()
        if "rss" in mime or "atom" in mime or "feed" in mime:
            href = link.get("href", "").strip()
            if href:
                return _abs_url(href, base_url)
    return None


async def discover_feed_url(site_url: str) -> Optional[str]:
    html = await _fetch_url(site_url)
    if not html:
        return None

    items = await parse_feed(html, site_url, limit=1)
    if items:
        return site_url

    discovered = _discover_feed_link_from_html(html, site_url)
    if discovered and discovered != site_url:
        content = await _fetch_url(discovered)
        if content:
            items = await parse_feed(content, discovered, limit=1)
            if items:
                return discovered

    origin = _origin(site_url)
    already_tried = {site_url, discovered}
    probe_urls = [origin + path for path in _FEED_PATHS if origin + path not in already_tried]

    _PROBE_SEM = asyncio.Semaphore(6)

    async def _try_probe(probe_url: str) -> Optional[str]:
        async with _PROBE_SEM:
            content = await _fetch_url(probe_url, timeout=8)
            if content:
                items = await parse_feed(content, probe_url, limit=1)
                if items:
                    return probe_url
        return None

    results = await asyncio.gather(*[_try_probe(u) for u in probe_urls])
    for r in results:
        if r:
            return r

    return None


_ARTICLE_LD_TYPES = {
    "article", "newsarticle", "blogposting", "socialmediaposting",
    "techarticle", "scholarlyarticle",
}


def _jsonld_node_to_item(node: dict, base_url: str, site_title: str) -> Optional[ParsedItem]:
    if not isinstance(node, dict):
        return None

    url_raw = node.get("url")
    if not url_raw:
        mep = node.get("mainEntityOfPage")
        url_raw = mep.get("@id") if isinstance(mep, dict) else mep
    url = _abs_url(str(url_raw), base_url) if url_raw else ""
    url = _strip_tracking_params(url) if url else url

    title = node.get("headline") or node.get("name") or ""
    desc = node.get("articleBody") or node.get("description") or node.get("abstract") or ""
    desc = _clean_description(desc) if desc else ""

    if not title and not url:
        return None
    if _is_junk_item(url, str(title)):
        return None

    published_at: Optional[datetime] = None
    raw_date = node.get("datePublished") or node.get("dateCreated")
    if raw_date:
        try:
            published_at = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
        except Exception:
            pass

    return ParsedItem(
        title=str(title),
        description=desc,
        url=url,
        published_at=published_at,
        source_title=site_title,
    )


def _extract_jsonld_items(html: str, base_url: str, limit: int, site_title: str) -> list[ParsedItem]:
    soup = BeautifulSoup(html, "html.parser")
    items: list[ParsedItem] = []

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = _json.loads(script.string or "")
        except Exception:
            continue

        raw_nodes = data if isinstance(data, list) else [data]
        nodes: list[dict] = []
        for raw in raw_nodes:
            if isinstance(raw, dict) and "@graph" in raw:
                nodes.extend(n for n in raw["@graph"] if isinstance(n, dict))
            elif isinstance(raw, dict):
                nodes.append(raw)

        for node in nodes:
            raw_type = node.get("@type") or ""
            if isinstance(raw_type, list):
                node_type = " ".join(str(t) for t in raw_type).lower()
            else:
                node_type = str(raw_type).lower()

            if node_type == "itemlist":
                for elem in node.get("itemListElement", []):
                    sub = elem.get("item", elem) if isinstance(elem, dict) else elem
                    item = _jsonld_node_to_item(sub, base_url, site_title)
                    if item:
                        items.append(item)
                        if len(items) >= limit:
                            return items

            elif any(t in node_type for t in _ARTICLE_LD_TYPES):
                item = _jsonld_node_to_item(node, base_url, site_title)
                if item:
                    items.append(item)
                    if len(items) >= limit:
                        return items

    return items


_MICRODATA_ARTICLE_TYPES = {
    "http://schema.org/Article", "http://schema.org/NewsArticle",
    "http://schema.org/BlogPosting", "https://schema.org/Article",
    "https://schema.org/NewsArticle", "https://schema.org/BlogPosting",
}


def _extract_microdata_items(html: str, base_url: str, limit: int, site_title: str) -> list[ParsedItem]:
    soup = BeautifulSoup(html, "html.parser")
    items: list[ParsedItem] = []

    for el in soup.find_all(attrs={"itemtype": True}):
        it = el.get("itemtype", "")
        if it not in _MICRODATA_ARTICLE_TYPES:
            continue

        def _itemprop(name: str) -> str:
            tag = el.find(attrs={"itemprop": name})
            if not tag:
                return ""
            return (tag.get("content") or tag.get("href") or tag.get_text(strip=True) or "").strip()

        title = _itemprop("headline") or _itemprop("name")
        if not title:
            continue
        url = _itemprop("url") or _itemprop("mainEntityOfPage")
        url = _abs_url(url, base_url) if url else ""
        url = _strip_tracking_params(url) if url else url
        desc = _clean_description(_itemprop("description"))

        if _is_junk_item(url, title):
            continue

        published_at: Optional[datetime] = None
        date_str = _itemprop("datePublished")
        if date_str:
            try:
                published_at = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except Exception:
                pass

        items.append(ParsedItem(
            title=title,
            description=desc,
            url=url,
            published_at=published_at,
            source_title=site_title,
        ))
        if len(items) >= limit:
            break

    return items


_ARTICLE_CLASS_RE = re.compile(
    r"\b(post|article|card|entry|item|blog-?post|news-?item|story|feed-?item)\b",
    re.I,
)


def _find_repeating_elements(soup: BeautifulSoup) -> list[Tag]:
    hints: list[Tag] = []
    for el in soup.find_all(["div", "li", "section"], class_=True):
        cls = " ".join(el.get("class", []))
        if _ARTICLE_CLASS_RE.search(cls):
            if el.find("a", href=True) and el.find(["h1", "h2", "h3", "h4", "strong"]):
                hints.append(el)
    if len(hints) >= 2:
        return hints

    counter: dict[tuple, list[Tag]] = {}
    for el in soup.find_all(["div", "li"], class_=True):
        key = (el.name, frozenset(el.get("class", [])))
        counter.setdefault(key, []).append(el)

    best: list[Tag] = []
    for siblings in counter.values():
        if len(siblings) >= 3:
            valid = [
                e for e in siblings
                if e.find("a", href=True) and e.find(["h1", "h2", "h3", "h4"])
            ]
            if len(valid) > len(best):
                best = valid

    return best


def _element_to_item(el: Tag, base_url: str, site_title: str) -> Optional[ParsedItem]:
    heading = el.find(["h1", "h2", "h3", "h4"])
    title = heading.get_text(strip=True) if heading else ""

    link_el = (heading.find("a", href=True) if heading else None) or el.find("a", href=True)
    href = (link_el["href"] if link_el else "") or ""
    url = _strip_tracking_params(_abs_url(href, base_url)) if href else ""

    if not title and not url:
        return None

    excerpt = ""
    for p in el.find_all("p"):
        t = p.get_text(strip=True)
        if len(t) > 40:
            excerpt = _clean_description(t)
            break

    published_at: Optional[datetime] = None
    time_el = el.find("time")
    if time_el:
        dt_str = time_el.get("datetime") or time_el.get_text(strip=True)
        if dt_str:
            try:
                published_at = datetime.fromisoformat(str(dt_str).replace("Z", "+00:00"))
            except Exception:
                pass

    return ParsedItem(
        title=title,
        description=excerpt,
        url=url,
        published_at=published_at,
        source_title=site_title,
    )


def _extract_html_articles(html: str, base_url: str, limit: int, site_title: str) -> list[ParsedItem]:
    soup = BeautifulSoup(html, "html.parser")

    candidates: list[Tag] = soup.find_all("article")
    if not candidates:
        candidates = _find_repeating_elements(soup)

    items: list[ParsedItem] = []
    seen_urls: set[str] = set()

    for el in candidates[:limit * 3]:
        item = _element_to_item(el, base_url, site_title)
        if item and item.url and item.url not in seen_urls:
            if not _is_junk_item(item.url, item.title):
                seen_urls.add(item.url)
                items.append(item)
        if len(items) >= limit:
            break

    return items


_PAGE_PARAM_RX = re.compile(r"[?&](page|p|pg|offset)=(\d+)", re.I)
_PAGE_PATH_RX = re.compile(r"/page/(\d+)")
_MAX_EXTRA_PAGES = 3


def _discover_pagination_urls(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    candidates: dict[int, str] = {}

    link_next = soup.find("link", rel="next")
    if link_next and link_next.get("href"):
        href = _abs_url(link_next["href"].strip(), base_url)
        m = _PAGE_PARAM_RX.search(href) or _PAGE_PATH_RX.search(href)
        if m:
            candidates[int(m.group(2) if _PAGE_PARAM_RX.match(m.group()) else m.group(1))] = href
        elif href != base_url:
            candidates[2] = href

    for container in soup.find_all(class_=re.compile(r"paginat|page-nav|pager|pages", re.I)):
        for a in container.find_all("a", href=True):
            href = _abs_url(a["href"].strip(), base_url)
            m = _PAGE_PARAM_RX.search(href)
            if m:
                candidates[int(m.group(2))] = href
                continue
            m = _PAGE_PATH_RX.search(href)
            if m:
                candidates[int(m.group(1))] = href

    if not candidates:
        parsed_base = urlparse(base_url)
        for a in soup.find_all("a", href=True):
            href = _abs_url(a["href"].strip(), base_url)
            if urlparse(href).netloc != parsed_base.netloc:
                continue
            m = _PAGE_PARAM_RX.search(href)
            if m:
                candidates[int(m.group(2))] = href
            else:
                m = _PAGE_PATH_RX.search(href)
                if m:
                    candidates[int(m.group(1))] = href

    result: list[str] = []
    for pg in sorted(candidates.keys()):
        if pg <= 1:
            continue
        result.append(candidates[pg])
        if len(result) >= _MAX_EXTRA_PAGES:
            break
    return result


async def _fetch_extra_pages(page_urls: list[str]) -> list[str]:
    _SEM = asyncio.Semaphore(6)

    async def _get(url: str) -> Optional[str]:
        async with _SEM:
            html = await _fetch_url(url, timeout=10)
            if html and len(html) > 500:
                return html
        return None

    results = await asyncio.gather(*[_get(u) for u in page_urls])
    return [r for r in results if r is not None]


_SITEMAP_PATHS = ["/sitemap.xml", "/news-sitemap.xml", "/sitemap-news.xml", "/post-sitemap.xml"]


async def _extract_sitemap_items(
    origin: str, base_url: str, limit: int, site_title: str,
) -> list[ParsedItem]:
    for path in _SITEMAP_PATHS:
        try:
            sm_xml = await _fetch_url(origin + path, timeout=8)
            if not sm_xml or "<urlset" not in sm_xml[:500]:
                continue
            soup = BeautifulSoup(sm_xml, "xml")
            urls_data: list[tuple[str, Optional[datetime]]] = []
            for url_tag in soup.find_all("url"):
                loc = url_tag.find("loc")
                if not loc or not loc.string:
                    continue
                link = loc.string.strip()
                if urlparse(link).netloc != urlparse(base_url).netloc:
                    continue
                if _normalize_url(link) == _normalize_url(base_url):
                    continue
                lastmod = None
                lm_tag = url_tag.find("lastmod")
                if lm_tag and lm_tag.string:
                    try:
                        lastmod = datetime.fromisoformat(lm_tag.string.strip().replace("Z", "+00:00"))
                    except Exception:
                        pass
                urls_data.append((_strip_tracking_params(link), lastmod))

            if not urls_data:
                continue

            urls_data.sort(key=lambda x: x[1] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
            items = []
            for link, published_at in urls_data[:limit]:
                path_parts = urlparse(link).path.strip("/").split("/")
                title_guess = path_parts[-1].replace("-", " ").replace("_", " ").title() if path_parts else ""
                items.append(ParsedItem(
                    title=title_guess,
                    url=link,
                    published_at=published_at,
                    source_title=site_title,
                ))
            logger.info("sitemap_found path=%s count=%d", path, len(items))
            return items
        except Exception:
            continue
    return []


def _merge_items(
    primary: list[ParsedItem],
    secondary: list[ParsedItem],
    limit: int,
    source_url: str = "",
) -> list[ParsedItem]:
    if not secondary:
        items = primary
    elif not primary:
        items = secondary
    else:
        seen: set[str] = set()
        items = []
        for it in primary:
            key = _normalize_url(it.url) if it.url else None
            if key:
                seen.add(key)
            items.append(it)
        for it in secondary:
            key = _normalize_url(it.url) if it.url else None
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            items.append(it)

    if source_url:
        src_norm = _normalize_url(source_url)
        items = [i for i in items if not i.url or _normalize_url(i.url) != src_norm]

    return items[:limit]


def _site_title(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for prop in ("og:site_name", "og:title"):
        tag = soup.find("meta", property=prop)
        if tag and tag.get("content"):
            return str(tag["content"])
    title_tag = soup.find("title")
    return title_tag.get_text(strip=True) if title_tag else ""


async def fetch_site_items(url: str, limit: int = 50) -> tuple[list[ParsedItem], Optional[str]]:
    html, status = await _fetch_url_with_status(url)
    if not html:
        if status in (401, 403, 503):
            gnews_items = await _try_google_news_rss(url, limit)
            if gnews_items:
                logger.info("google_news_fallback url=%s count=%d (blocked with %d)", url, len(gnews_items), status)
                return gnews_items, None
        return [], None

    final_url = url

    items = await parse_feed(html, url, limit)
    if items:
        logger.info("native_feed url=%s count=%d", url, len(items))
        return items, url

    discovered = _discover_feed_link_from_html(html, final_url)
    if discovered and discovered != url:
        content = await _fetch_url(discovered)
        if content:
            items = await parse_feed(content, discovered, limit)
            if items:
                logger.info("autodiscovered_feed url=%s feed=%s count=%d", url, discovered, len(items))
                return items, discovered

    origin = _origin(final_url)
    already_tried = {url, discovered}
    probe_urls = [origin + path for path in _FEED_PATHS if origin + path not in already_tried]

    if probe_urls:
        _PROBE_SEM = asyncio.Semaphore(6)

        async def _try_probe(probe_url: str) -> Optional[tuple[list[ParsedItem], str]]:
            async with _PROBE_SEM:
                content = await _fetch_url(probe_url, timeout=5)
                if content:
                    pitems = await parse_feed(content, probe_url, limit)
                    if pitems:
                        return pitems, probe_url
            return None

        probe_results = await asyncio.gather(*[_try_probe(u) for u in probe_urls])
        for result in probe_results:
            if result:
                pitems, feed_url = result
                logger.info("probe_feed url=%s feed=%s count=%d", url, feed_url, len(pitems))
                return pitems, feed_url

    title = _site_title(html)

    page_urls = _discover_pagination_urls(html, final_url)
    extra_htmls: list[str] = []
    if page_urls:
        extra_htmls = await _fetch_extra_pages(page_urls)
        if extra_htmls:
            logger.info("pagination_fetched url=%s pages=%d", url, len(extra_htmls))
    all_htmls = [html] + extra_htmls

    jsonld: list[ParsedItem] = []
    microdata: list[ParsedItem] = []
    for page_html in all_htmls:
        jsonld.extend(_extract_jsonld_items(page_html, final_url, limit, title))
        microdata.extend(_extract_microdata_items(page_html, final_url, limit, title))
    structured = _merge_items(jsonld, microdata, limit, source_url=final_url)

    scraped: list[ParsedItem] = []
    if len(structured) < limit:
        for page_html in all_htmls:
            scraped.extend(_extract_html_articles(page_html, final_url, limit, title))

    items = _merge_items(structured, scraped, limit, source_url=final_url)

    if len(items) < 3:
        sitemap_items = await _extract_sitemap_items(origin, final_url, limit, title)
        items = _merge_items(items, sitemap_items, limit, source_url=final_url)

    if len(items) < 5:
        gnews_items = await _try_google_news_rss(url, limit)
        if gnews_items:
            if not items:
                logger.info("google_news_fallback url=%s count=%d (no direct content)", url, len(gnews_items))
                return gnews_items, None
            items = _merge_items(items, gnews_items, limit, source_url=final_url)
            logger.info("google_news_supplement url=%s direct=%d gnews=%d total=%d",
                         url, len(items) - len(gnews_items), len(gnews_items), len(items))

    if items:
        logger.info("html_extracted url=%s jsonld=%d microdata=%d scraped=%d total=%d",
                     url, len(jsonld), len(microdata), len(scraped), len(items))
    else:
        logger.warning("no_content_found url=%s", url)

    return items, None
