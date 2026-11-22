#!/usr/bin/env python3
"""Sync IGI-tagged/sectioned Substack posts into data/posts.json and index.html.

Uses only the Python standard library so CI requires zero pip dependencies:
1. Pulls the hourly PIRL Google Cloud Substack cache (which avoids Substack's
   HTTP 403 blocks on GitHub Actions runner IPs).
2. Optionally probes the Substack IGI section RSS (/s/igi/feed) and tag page
   (/t/igi) when reachable (e.g. once created in Substack or when run locally).
3. Filters posts to IGI via section/tag membership, `include_urls`, or
   `match_patterns` in `data/blog_config.json` (minus `exclude_urls`).
4. Caches real post cover images under `assets/posts/` (skipping generic
   publication-avatar fallbacks) and renders the feed block into `index.html`.
"""

import argparse
import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "data" / "blog_config.json"
POSTS_PATH = ROOT / "data" / "posts.json"
INDEX_PATH = ROOT / "index.html"
START_MARKER = "<!-- BLOG-POSTS:START -->"
END_MARKER = "<!-- BLOG-POSTS:END -->"
MAX_ARCHIVE_BYTES = 100 * 1024 * 1024
MAX_FEED_BYTES = 12 * 1024 * 1024
ALLOWED_TAR_MEMBER = re.compile(
    r"^(data/posts\.json|data/posts_status\.json|static/assets/posts(/[A-Za-z0-9._-]+)?/?)$"
)
NS = {
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "media": "http://search.yahoo.com/mrss/",
}


def clean_url(url: str) -> str:
    if not url:
        return ""
    parts = urlsplit(url.strip())
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return ""
    return f"{parts.scheme}://{parts.netloc}{parts.path.rstrip('/')}"


def fetch_bytes(url: str, max_bytes: int = MAX_FEED_BYTES) -> bytes:
    if shutil.which("curl"):
        res = subprocess.run(
            [
                "curl", "--silent", "--show-error", "--fail", "--location",
                "--proto", "=http,https", "--proto-redir", "=http,https",
                "--max-time", "25", "--max-filesize", str(max_bytes), url,
            ],
            capture_output=True,
        )
        if res.returncode != 0:
            raise OSError(res.stderr.decode(errors="replace").strip() or f"curl exit {res.returncode}")
        return res.stdout
    req = urllib.request.Request(url, headers={"User-Agent": "igi-site-sync/1.0 (+https://igi-unc.github.io)"})
    with urllib.request.urlopen(req, timeout=25) as resp:
        data = resp.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError("Response too large")
    return data


class SimpleFeedHTML(HTMLParser):
    def __init__(self, markup: str):
        super().__init__(convert_charrefs=True)
        self.words: list[str] = []
        self.images: list[str] = []
        self._skip = 0
        self.feed(markup or "")

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag in {"script", "style"}:
            self._skip += 1
            return
        if self._skip:
            return
        if tag in {"p", "br", "div", "li"}:
            self.words.append(" ")
        if tag == "img" and d.get("width") not in {"0", "1"} and d.get("height") not in {"0", "1"}:
            src = d.get("src") or d.get("data-src") or ""
            if src:
                self.images.append(src)

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self._skip = max(0, self._skip - 1)
        elif tag in {"p", "div", "li"}:
            self.words.append(" ")

    def handle_data(self, data):
        if not self._skip:
            self.words.append(data)

    @property
    def text(self) -> str:
        return " ".join("".join(self.words).split())


def short_excerpt(value: str, max_words: int = 45) -> str:
    words = (value or "").split()
    return " ".join(words[:max_words]) + ("…" if len(words) > max_words else "")


def parse_rss(xml_bytes: bytes) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    channel = root.find("channel")
    if channel is None:
        return []
    out = []
    for item in channel.findall("item"):
        title = (item.findtext("title") or "").strip()
        link = clean_url(item.findtext("link") or "")
        if not title or not link:
            continue
        desc = SimpleFeedHTML(item.findtext("description") or "")
        body = SimpleFeedHTML(item.findtext("content:encoded", default="", namespaces=NS) or "")
        imgs = []
        for enc in item.findall("enclosure"):
            if (enc.get("type") or "").startswith("image/") and enc.get("url"):
                imgs.append(enc.get("url"))
        imgs.extend(body.images + desc.images)
        image = next((urljoin(link, u) for u in imgs if u and urlsplit(urljoin(link, u)).scheme in {"http", "https"}), "")
        date_iso = ""
        try:
            date_iso = parsedate_to_datetime((item.findtext("pubDate") or "").strip()).date().isoformat()
        except Exception:
            pass
        out.append({
            "title": title,
            "subtitle": desc.text[:320],
            "url": link,
            "date": date_iso,
            "author": (item.findtext("dc:creator", default="", namespaces=NS) or "").strip(),
            "image": image,
            "excerpt": short_excerpt(body.text or desc.text),
        })
    return out


def pull_gcs_archive(url: str, dest: Path) -> list[dict]:
    archive = dest / "cache.tgz"
    archive.write_bytes(fetch_bytes(url, max_bytes=MAX_ARCHIVE_BYTES))
    extracted = dest / "extracted"
    extracted.mkdir()
    with tarfile.open(archive) as tar:
        members = tar.getmembers()
        for m in members:
            if not ALLOWED_TAR_MEMBER.match(m.name) or not (m.isfile() or m.isdir()):
                raise ValueError(f"Unexpected tar member: {m.name}")
        tar.extractall(extracted, members=members, filter="data")
    posts = json.loads((extracted / "data" / "posts.json").read_text(encoding="utf-8"))
    for p in posts:
        p["url"] = clean_url(p.get("url", ""))
        rel = p.get("image_local", "")
        if rel:
            src_file = extracted / "static" / rel
            if src_file.is_file():
                p["_staged_cover"] = str(src_file)
    return posts


def probe_tag_urls(tag_page_url: str, blog_url: str) -> set[str]:
    if not tag_page_url:
        return set()
    try:
        page = fetch_bytes(tag_page_url).decode("utf-8", errors="replace")
    except Exception:
        return set()
    # Ignore redirect to the publication root when the tag does not exist yet.
    if "/p/" not in page:
        return set()
    base = blog_url.rstrip("/")
    found = set()
    for slug in re.findall(r"(?:https://pirlblog\.substack\.com)?(/p/[a-z0-9-]+)", page):
        found.add(clean_url(base + slug))
    return found


def is_igi_post(post: dict, config: dict, tagged_urls: set[str]) -> bool:
    url = clean_url(post.get("url", ""))
    if not url:
        return False
    excluded = {clean_url(u) for u in config.get("exclude_urls", [])}
    if url in excluded:
        return False
    included = {clean_url(u) for u in config.get("include_urls", [])}
    if url in included or url in tagged_urls:
        return True
    haystack = " ".join(
        str(post.get(k) or "") for k in ("title", "subtitle", "excerpt")
    )
    for pat in config.get("match_patterns", []):
        flags = 0 if pat == r"\bIGI\b" else re.IGNORECASE
        if re.search(pat, haystack, flags):
            return True
    return False


def image_ext(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data[:6] in {b"GIF87a", b"GIF89a"}:
        return ".gif"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return ".webp"
    return ""


def usable_cover(post: dict, config: dict) -> bool:
    for url_key in ("image", "image_cached_url"):
        val = post.get(url_key) or ""
        if any(sub in val for sub in config.get("ignore_image_substrings", [])):
            return False
    return bool(post.get("image") or post.get("_staged_cover") or post.get("image_local"))


def materialize_covers(posts: list[dict], config: dict) -> None:
    covers_dir = ROOT / "assets" / "posts"
    covers_dir.mkdir(parents=True, exist_ok=True)
    keep_files: set[str] = set()

    for post in posts:
        staged = post.pop("_staged_cover", None)
        if not usable_cover(post, config):
            post.pop("image_local", None)
            continue

        existing_rel = post.get("image_local", "")
        if existing_rel and existing_rel.startswith("assets/posts/") and (ROOT / existing_rel).is_file():
            keep_files.add(Path(existing_rel).name)
            continue

        if staged and Path(staged).is_file():
            name = Path(staged).name
            dest = covers_dir / name
            shutil.copy2(staged, dest)
            post["image_local"] = f"assets/posts/{name}"
            keep_files.add(name)
            continue

        img_url = post.get("image") or ""
        if img_url:
            try:
                raw = fetch_bytes(img_url)
                ext = image_ext(raw)
                if ext:
                    name = hashlib.sha256(img_url.encode()).hexdigest()[:20] + ext
                    (covers_dir / name).write_bytes(raw)
                    post["image_local"] = f"assets/posts/{name}"
                    keep_files.add(name)
            except Exception:
                post.pop("image_local", None)

    for f in covers_dir.iterdir():
        if f.is_file() and f.name not in keep_files:
            f.unlink()


def nice_date(iso_str: str) -> str:
    if not iso_str:
        return ""
    try:
        d = date.fromisoformat(iso_str[:10])
        return f"{d.strftime('%b')} {d.day}, {d.year}"
    except ValueError:
        return iso_str


def render_posts_html(posts: list[dict], blog_url: str) -> str:
    if not posts:
        esc_blog = html.escape(blog_url, quote=True)
        return (
            f'      <p class="feed-empty">Read updates and research notes on the '
            f'<a href="{esc_blog}">Substack blog</a>.</p>'
        )

    items = ['      <ol class="post-list">']
    for post in posts:
        url = html.escape(post["url"], quote=True)
        title = html.escape(post["title"])
        date_iso = html.escape(post.get("date", ""), quote=True)
        date_human = html.escape(nice_date(post.get("date", "")))
        author = html.escape(post.get("author", ""))
        summary_raw = post.get("subtitle") or post.get("excerpt") or ""
        summary = html.escape(short_excerpt(summary_raw, max_words=38))
        cover_rel = post.get("image_local") or ""

        meta_parts = []
        if date_human:
            meta_parts.append(f'<time datetime="{date_iso}">{date_human}</time>')
        if author:
            meta_parts.append(f"<span>{author}</span>")
        meta_html = " · ".join(meta_parts)

        has_cover = bool(cover_rel and (ROOT / cover_rel).is_file())
        cls = "post-card has-cover" if has_cover else "post-card"
        items.append(f'        <li class="{cls}">')
        items.append('          <div class="post-text">')
        if meta_html:
            items.append(f'            <div class="post-meta">{meta_html}</div>')
        items.append(f'            <h3><a href="{url}">{title}</a></h3>')
        if summary:
            items.append(f"            <p>{summary}</p>")
        items.append("          </div>")
        if has_cover:
            esc_cover = html.escape("/" + cover_rel.lstrip("/"), quote=True)
            items.append(
                f'          <a class="post-thumb" href="{url}" tabindex="-1" aria-hidden="true">'
                f'<img src="{esc_cover}" alt="" loading="lazy"></a>'
            )
        items.append("        </li>")
    items.append("      </ol>")
    return "\n".join(items)


def inject_into_index(index_html: str, rendered_block: str) -> str:
    if START_MARKER not in index_html or END_MARKER not in index_html:
        raise ValueError("index.html is missing BLOG-POSTS markers")
    before, rest = index_html.split(START_MARKER, 1)
    _, after = rest.split(END_MARKER, 1)
    return f"{before}{START_MARKER}\n{rendered_block}\n      {END_MARKER}{after}"


def load_cached_posts() -> list[dict]:
    if not POSTS_PATH.is_file():
        return []
    try:
        return json.loads(POSTS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def sync(offline: bool = False) -> int:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    by_url: dict[str, dict] = {}
    tagged_urls: set[str] = set()

    if offline:
        for p in load_cached_posts():
            u = clean_url(p.get("url", ""))
            if u:
                by_url[u] = p
    else:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            gcs_url = config.get("gcs_cache_url", "")
            if gcs_url:
                try:
                    for p in pull_gcs_archive(gcs_url, tmp):
                        if p.get("url"):
                            by_url[p["url"]] = p
                except Exception as exc:
                    print(f"Warning: GCS cache unavailable ({exc})", file=sys.stderr)

            sec_url = config.get("section_feed_url", "")
            if sec_url:
                try:
                    for p in parse_rss(fetch_bytes(sec_url)):
                        tagged_urls.add(p["url"])
                        by_url.setdefault(p["url"], p)
                except Exception:
                    pass

            tagged_urls |= probe_tag_urls(config.get("tag_page_url", ""), config.get("blog_url", ""))

            if not by_url:
                rss_url = config.get("rss_url", "")
                if rss_url:
                    try:
                        for p in parse_rss(fetch_bytes(rss_url)):
                            by_url[p["url"]] = p
                    except Exception as exc:
                        print(f"Warning: RSS feed unavailable ({exc})", file=sys.stderr)

            if not by_url:
                for p in load_cached_posts():
                    u = clean_url(p.get("url", ""))
                    if u:
                        by_url[u] = p

            selected = [
                p for p in by_url.values()
                if is_igi_post(p, config, tagged_urls)
            ]
            selected.sort(key=lambda p: p.get("date") or "", reverse=True)
            selected = selected[: config.get("max_posts", 6)]
            materialize_covers(selected, config)

    if offline:
        selected = [
            p for p in by_url.values()
            if is_igi_post(p, config, tagged_urls)
        ]
        selected.sort(key=lambda p: p.get("date") or "", reverse=True)
        selected = selected[: config.get("max_posts", 6)]

    clean_records = []
    for p in selected:
        rec = {
            "title": p["title"].strip(),
            "subtitle": (p.get("subtitle") or "").strip(),
            "url": p["url"],
            "date": p.get("date") or "",
            "author": (p.get("author") or "").strip(),
            "excerpt": (p.get("excerpt") or "").strip(),
        }
        if p.get("image_local"):
            rec["image_local"] = p["image_local"]
        clean_records.append(rec)

    POSTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    POSTS_PATH.write_text(json.dumps(clean_records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    rendered = render_posts_html(clean_records, config.get("blog_url", "https://pirlblog.substack.com"))
    updated_index = inject_into_index(INDEX_PATH.read_text(encoding="utf-8"), rendered)
    INDEX_PATH.write_text(updated_index, encoding="utf-8")
    print(f"Synced {len(clean_records)} IGI post(s) into index.html")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--offline", action="store_true", help="Render from existing data/posts.json without network")
    sys.exit(sync(offline=ap.parse_args().offline))
