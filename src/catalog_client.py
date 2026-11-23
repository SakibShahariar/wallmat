"""Network client for the optional Wikimedia Commons catalog (#75).

All network work runs in daemon threads and reports back through GLib so the
GTK main loop is never blocked. Requests use the public API with a descriptive
User-Agent and a conservative one-request-per-second rate.
"""

import hashlib
import json
import os
import tempfile
import threading
import time
import urllib.error
import urllib.request

from catalog_commons import (
    USER_AGENT, build_search_url, parse_search_response, safe_filename,
    validate_download_url,
)

MAX_DOWNLOAD_BYTES = 40 * 1024 * 1024
MIN_REQUEST_INTERVAL = 2.0
CHUNK_SIZE = 64 * 1024
PREVIEW_MAX_BYTES = 3 * 1024 * 1024
# Previews are tiny 400 px thumbnails; use a lighter rate than full downloads
# so a page of results does not take half a minute to populate.
PREVIEW_MIN_REQUEST_INTERVAL = 0.3
_rate_lock = threading.Lock()
_last_request = [0.0]
_preview_rate_lock = threading.Lock()
_last_preview_request = [0.0]


def _throttle():
    """Respect the provider's conservative anonymous request rate."""
    with _rate_lock:
        wait = MIN_REQUEST_INTERVAL - (time.monotonic() - _last_request[0])
        if wait > 0:
            time.sleep(wait)
        _last_request[0] = time.monotonic()


def _fetch(url, timeout=20):
    """Fetch one URL, respecting the provider's rate limits."""
    for attempt in range(4):
        _throttle()
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response, response.read()
        except urllib.error.HTTPError as error:
            if error.code != 429 or attempt == 3:
                raise
            # Honour Retry-After when present, otherwise back off politely.
            delay = 5.0 * (2 ** attempt)
            try:
                delay = max(delay, float(error.headers.get("Retry-After", delay)))
            except (TypeError, ValueError):
                pass
            time.sleep(min(delay, 30.0))
    raise RuntimeError("rate limited by the catalog provider")


def search(query, callback, limit=12, max_bytes=MAX_DOWNLOAD_BYTES):
    """Fetch matching catalog items; callback(items, error) on the GTK thread."""
    from gi.repository import GLib

    def work():
        try:
            url = build_search_url(query, limit)
            _response, body = _fetch(url)
            items = parse_search_response(json.loads(body.decode("utf-8")), max_bytes)
            GLib.idle_add(callback, items, None)
        except Exception as error:
            GLib.idle_add(callback, [], str(error))

    threading.Thread(target=work, daemon=True, name="wallmat-catalog-search").start()


def _decode_image(path):
    """Return True when the downloaded file decodes as a supported image."""
    import gi
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GdkPixbuf
    try:
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 16, 16, True)
        return pixbuf is not None
    except Exception:
        return False


def download(item, target_dir, callback, max_bytes=MAX_DOWNLOAD_BYTES):
    """Download one item atomically into target_dir.

    callback(path, error) is called on the GTK thread. No existing file is
    overwritten; collisions get a numeric suffix.
    """
    from gi.repository import GLib

    def work():
        temporary = None
        try:
            if not validate_download_url(item.get("download_url", "")):
                raise ValueError("unsafe catalog download URL")
            os.makedirs(target_dir, exist_ok=True)
            response, body = _fetch(item["download_url"], timeout=60)
            # urllib follows redirects; validate where we actually landed so
            # a Commons URL cannot bounce to an untrusted host.
            if not validate_download_url(response.geturl()):
                raise ValueError("redirect led to an unsafe download host")
            if len(body) > max_bytes:
                raise ValueError("download exceeds the size limit")
            if not body:
                raise ValueError("empty download")

            base = safe_filename(item.get("title", "wallpaper"))
            root, ext = os.path.splitext(base)
            ext = ext.lower() if ext in (".jpg", ".jpeg", ".png", ".webp") else ".jpg"
            final = os.path.join(target_dir, root + ext)
            counter = 1
            while os.path.exists(final):
                final = os.path.join(target_dir, f"{root}-{counter}{ext}")
                counter += 1

            fd, temporary = tempfile.mkstemp(
                prefix=".wallmat-download-", suffix=ext, dir=target_dir
            )
            with os.fdopen(fd, "wb") as handle:
                handle.write(body)
                handle.flush()
                os.fsync(handle.fileno())
            if not _decode_image(temporary):
                raise ValueError("downloaded file is not a supported image")
            os.replace(temporary, final)
            temporary = None
            GLib.idle_add(callback, final, None)
        except Exception as error:
            GLib.idle_add(callback, None, str(error))
        finally:
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except OSError:
                    pass

    threading.Thread(target=work, daemon=True, name="wallmat-catalog-download").start()


def _preview_cache_path(url):
    """Return a stable cache path for a preview URL."""
    cache_dir = os.path.join(tempfile.gettempdir(), "wallmat-catalog-previews")
    os.makedirs(cache_dir, exist_ok=True)
    name = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24] + ".img"
    return os.path.join(cache_dir, name)


def fetch_preview(url, callback):
    """Fetch a small catalog thumbnail; callback(path, error) on the GTK thread.

    Previews are cached on disk, so reopening a search does not re-download
    them. Only validated Wikimedia image URLs are accepted.
    """
    from gi.repository import GLib

    def work():
        temporary = None
        try:
            if not validate_download_url(url):
                raise ValueError("unsafe catalog preview URL")
            path = _preview_cache_path(url)
            if os.path.exists(path) and _decode_image(path):
                GLib.idle_add(callback, path, None)
                return
            with _preview_rate_lock:
                wait = PREVIEW_MIN_REQUEST_INTERVAL - (
                    time.monotonic() - _last_preview_request[0]
                )
                if wait > 0:
                    time.sleep(wait)
                _last_preview_request[0] = time.monotonic()
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=20) as response:
                body = response.read(PREVIEW_MAX_BYTES + 1)
            if len(body) > PREVIEW_MAX_BYTES:
                raise ValueError("preview exceeds the size limit")
            if not body:
                raise ValueError("empty preview")
            fd, temporary = tempfile.mkstemp(
                prefix=".wallmat-preview-", dir=os.path.dirname(path)
            )
            with os.fdopen(fd, "wb") as handle:
                handle.write(body)
            if not _decode_image(temporary):
                raise ValueError("preview is not a supported image")
            os.replace(temporary, path)
            temporary = None
            GLib.idle_add(callback, path, None)
        except Exception as error:
            GLib.idle_add(callback, None, str(error))
        finally:
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except OSError:
                    pass

    threading.Thread(target=work, daemon=True, name="wallmat-catalog-preview").start()
