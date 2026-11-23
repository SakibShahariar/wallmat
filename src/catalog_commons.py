"""Wikimedia Commons catalog adapter for optional online wallpaper import (#75).

The parsing and URL-safety helpers are pure so they can be tested in CI. The
network client in ``catalog_client`` is the only part that performs requests;
it uses the public MediaWiki API with a descriptive User-Agent, a conservative
request rate, and no credentials or tracking.
"""

import html
import re
from urllib.parse import quote, urlencode, urlparse

API_URL = "https://commons.wikimedia.org/w/api.php"
WIKI_URL = "https://commons.wikimedia.org/wiki/"
USER_AGENT = "Wallmat/1.0 (wallpaper chooser; public MediaWiki API)"

# Only Wikimedia's own upload hosts may be downloaded from. This blocks
# arbitrary redirects to third-party hosts and credential-bearing URLs.
ALLOWED_DOWNLOAD_HOSTS = frozenset({
    "upload.wikimedia.org", "thumb.wikimedia.org",
})
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")


def build_search_url(query, limit=12):
    """Return a MediaWiki API search URL for JPEG/PNG/WebP image files."""
    limit = max(1, min(int(limit), 20))
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": f"filetype:bitmap {query}",
        "gsrnamespace": 6,
        "gsrlimit": limit,
        "prop": "imageinfo",
        "iiprop": "url|extmetadata|size",
        "iiurlwidth": 800,
        "format": "json",
    }
    return f"{API_URL}?{urlencode(params)}"


def _strip_html(value):
    """Return plain text from a Commons extmetadata HTML value."""
    if not value:
        return ""
    text = re.sub(r"<[^>]+>", " ", str(value))
    return " ".join(html.unescape(text).split())


def validate_download_url(url):
    """Return whether a URL is a safe HTTPS Wikimedia image download."""
    if not isinstance(url, str) or not url:
        return False
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.username or parsed.password:
        return False
    if parsed.hostname not in ALLOWED_DOWNLOAD_HOSTS:
        return False
    path = parsed.path.lower()
    if not any(path.endswith(ext) for ext in IMAGE_EXTENSIONS):
        return False
    # Commons sometimes appends tracking query parameters; drop them rather
    # than forward them to the download or store them in metadata.
    return True


def clean_download_url(url):
    """Strip tracking query parameters from a Commons download URL."""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


def description_url(title):
    """Return the Commons description page URL for a file title."""
    return WIKI_URL + quote(title.replace(" ", "_"), safe="()_',.!-")


def parse_search_response(payload, max_bytes=40 * 1024 * 1024):
    """Turn a MediaWiki API response into validated catalog items.

    Results missing required attribution metadata, using an unsafe URL or
    exceeding the size cap are dropped rather than shown as unusable rows.
    """
    if not isinstance(payload, dict):
        raise ValueError("catalog response must be a JSON object")
    pages = payload.get("query", {}).get("pages", {})
    if not isinstance(pages, dict):
        raise ValueError("catalog response has invalid pages")
    items = []
    for page in pages.values():
        if not isinstance(page, dict):
            continue
        info = (page.get("imageinfo") or [{}])[0]
        if not isinstance(info, dict):
            continue
        url = clean_download_url(info.get("url") or "")
        if not validate_download_url(url):
            continue
        size = info.get("size")
        if type(size) is not int or size <= 0 or size > max_bytes:
            continue
        meta = info.get("extmetadata") or {}
        def field(name):
            return _strip_html(meta.get(name, {}).get("value"))
        license_name = field("LicenseShortName")
        if not license_name:
            continue
        title = page.get("title") or ""
        items.append({
            "title": title,
            "download_url": url,
            "preview_url": clean_download_url(info.get("thumburl") or url),
            "size": size,
            "width": info.get("width"),
            "height": info.get("height"),
            "artist": field("Artist") or "Unknown",
            "license": license_name,
            "license_url": field("LicenseUrl"),
            "attribution_required": field("AttributionRequired").lower() == "true",
            "description_url": description_url(title),
        })
    return items


def safe_filename(title):
    """Build a conservative local filename from a Commons file title."""
    name = title.split(":", 1)[-1] if ":" in title else title
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", name)
    name = re.sub(r"_+", "_", name).strip(" ._") or "wallpaper"
    name = re.sub(r"_\.([A-Za-z0-9]+)$", r".\1", name)
    return name[:120]


def attribution_text(item):
    """Return a human-readable attribution line for a catalog item."""
    parts = [f"Creator: {item.get('artist') or 'Unknown'}",
             f"License: {item.get('license') or 'Unknown'}"]
    if item.get("license_url"):
        parts.append(f"License details: {item['license_url']}")
    if item.get("description_url"):
        parts.append(f"Source: {item['description_url']}")
    return "\n".join(parts)
