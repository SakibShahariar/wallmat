"""
Async thumbnail loader.

- Debounces load requests: an item must stay "in view" for 100ms before
  a decode is actually queued, so fast scrolling doesn't pile up work
  for thumbnails that are already off-screen again.
- Caps concurrent decode operations (default 3) to avoid I/O/CPU thrashing
  on older hardware.
- Falls back from WebP -> PNG/JPEG automatically based on what's cached,
  and checks libwebp availability once at startup.
"""

import os
import hashlib
import threading
import queue
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GLib, Gdk, GdkPixbuf, Gio


CACHE_DIR = os.path.expanduser("~/.cache/wallpaper-chooser/thumbs")
THUMB_SIZE = 900  # bumped again: fill_height mode (Infinite Ribbon) can
                   # stretch cards to most of the window's height, well
                   # beyond what 480px was designed for — this is a shared
                   # constant across all layouts using ThumbnailLoader, so
                   # raising it also sharpens the others, at the cost of
                   # slightly more decode time/memory per thumbnail. The
                   # cache key already includes THUMB_SIZE (see
                   # _cache_path below), so old 480px cached files won't
                   # be reused — first load after this change re-decodes
                   # everything.
DEBOUNCE_MS = 100
MAX_CONCURRENT_DECODES = 3


def webp_supported() -> bool:
    formats = GdkPixbuf.Pixbuf.get_formats()
    return any(fmt.get_name() == "webp" for fmt in formats)


class ThumbnailLoader:
    """
    Usage:
        loader = ThumbnailLoader()
        loader.request(item_id, source_path, on_ready=callback)
        # ... later, if the item scrolls off-screen before 100ms elapses:
        loader.cancel(item_id)
    """

    def __init__(self, max_concurrent: int = MAX_CONCURRENT_DECODES):
        os.makedirs(CACHE_DIR, exist_ok=True)
        self._webp_ok = webp_supported()
        self._cache_ext = "webp" if self._webp_ok else "png"

        self._max_concurrent = max_concurrent
        self._sema = threading.Semaphore(max_concurrent)

        # item_id -> GLib timeout source id, for pending debounced requests
        self._pending_timeouts: dict[str, int] = {}
        # item_id -> True while a decode thread is in flight, for cancellation checks
        self._in_flight: dict[str, bool] = {}

    # -- public API --

    def request(self, item_id: str, source_path: str, on_ready):
        """
        Schedule a debounced load. `on_ready(item_id, Gdk.Texture)` is
        called on the GLib main thread once decoding finishes.
        """
        self.cancel(item_id)  # clear any prior pending timeout for this item

        def fire_after_debounce():
            self._pending_timeouts.pop(item_id, None)
            self._start_decode(item_id, source_path, on_ready)
            return GLib.SOURCE_REMOVE

        timeout_id = GLib.timeout_add(DEBOUNCE_MS, fire_after_debounce)
        self._pending_timeouts[item_id] = timeout_id

    def cancel(self, item_id: str):
        """Call when an item scrolls out of view before its debounce fires."""
        timeout_id = self._pending_timeouts.pop(item_id, None)
        if timeout_id is not None:
            GLib.source_remove(timeout_id)
        # Note: in-flight decode threads are left to finish (cheap, bounded
        # by MAX_CONCURRENT_DECODES) but their result is simply not applied
        # if the caller's on_ready checks the item is still bound/visible.
        self._in_flight.pop(item_id, None)

    # -- internal --

    def _cache_path(self, source_path: str) -> str:
        try:
            mtime = os.path.getmtime(source_path)
        except OSError:
            mtime = 0
        # THUMB_SIZE is part of the key so changing it (e.g. for sharper
        # thumbnails) invalidates old cached sizes automatically instead
        # of silently reusing a lower-resolution cached file forever.
        key = f"{source_path}:{mtime}:{THUMB_SIZE}"
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return os.path.join(CACHE_DIR, f"{digest}.{self._cache_ext}")

    def _start_decode(self, item_id: str, source_path: str, on_ready):
        self._in_flight[item_id] = True
        thread = threading.Thread(
            target=self._decode_worker,
            args=(item_id, source_path, on_ready),
            daemon=True,
        )
        thread.start()

    def _decode_worker(self, item_id: str, source_path: str, on_ready):
        with self._sema:  # cap concurrent decodes
            if not self._in_flight.get(item_id):
                return  # cancelled while waiting for a semaphore slot

            cache_path = self._cache_path(source_path)
            try:
                if os.path.exists(cache_path):
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file(cache_path)
                else:
                    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                        source_path, THUMB_SIZE, -1, True
                    )
                    try:
                        pixbuf.savev(cache_path, self._cache_ext, [], [])
                    except GLib.Error:
                        pass  # cache write failure is non-fatal
            except GLib.Error:
                return

            if not self._in_flight.get(item_id):
                return  # cancelled mid-decode; drop result

            # Hand off to the main thread for GTK/Gdk object creation
            GLib.idle_add(self._deliver, item_id, pixbuf, on_ready)

    def _deliver(self, item_id, pixbuf, on_ready):
        self._in_flight.pop(item_id, None)
        texture = Gdk.Texture.new_for_pixbuf(pixbuf)
        on_ready(item_id, texture)
        return GLib.SOURCE_REMOVE
