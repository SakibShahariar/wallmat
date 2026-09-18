"""
Async thumbnail loader.

- Debounces load requests: an item must stay "in view" for 100ms before
  a decode is actually queued, so fast scrolling doesn't pile up work
  for thumbnails that are already off-screen again.
- Decoding runs on a small FIXED pool of worker threads (default 3),
  not one OS thread per request. An earlier version spawned a new
  threading.Thread for every debounced request and only capped
  *concurrent decodes* with a semaphore — every other in-flight request
  still got a live blocked thread, so a burst of requests (fast
  scrolling a large folder) could spawn dozens of threads at once. This
  app's Rust rewrite hit the same "thread storm from unbounded thread
  spawning" issue and fixed it with a fixed-size worker pool; this
  ports that same fix back here.
- Falls back from WebP -> PNG/JPEG automatically based on what's cached,
  and checks libwebp availability once at startup.
- Thumbnail size is per-instance (`thumb_size`), not a single global
  constant shared by every layout — a small grid cell and a full-height
  ribbon card have very different resolution needs, and decoding/caching
  everything at the size the largest case needs wastes CPU, disk, and
  texture memory for the smaller ones.
"""

import os
import hashlib
import threading
import queue

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GLib, Gdk, GdkPixbuf


CACHE_DIR = os.path.expanduser("~/.cache/wallpaper-chooser/thumbs")
DEFAULT_THUMB_SIZE = 480
DEBOUNCE_MS = 100
POOL_SIZE = 3


def webp_supported() -> bool:
    formats = GdkPixbuf.Pixbuf.get_formats()
    return any(fmt.get_name() == "webp" for fmt in formats)


class ThumbnailLoader:
    """
    Usage:
        loader = ThumbnailLoader(thumb_size=480)
        loader.request(item_id, source_path, on_ready=callback)
        # ... later, if the item scrolls off-screen before 100ms elapses:
        loader.cancel(item_id)
    """

    def __init__(self, max_concurrent: int = POOL_SIZE, thumb_size: int = DEFAULT_THUMB_SIZE):
        os.makedirs(CACHE_DIR, exist_ok=True)
        self._webp_ok = webp_supported()
        self._cache_ext = "webp" if self._webp_ok else "png"
        self._thumb_size = thumb_size

        # item_id -> GLib timeout source id, for pending debounced requests
        self._pending_timeouts: dict[str, int] = {}
        # item_id -> True while queued or being decoded. cancel() removes
        # the entry; a worker that dequeues a job whose item_id is no
        # longer here drops the job instead of decoding/delivering it.
        self._live: dict[str, bool] = {}

        self._job_queue: "queue.Queue" = queue.Queue()
        self._workers = []
        for _ in range(max(1, max_concurrent)):
            t = threading.Thread(target=self._worker_loop, daemon=True)
            t.start()
            self._workers.append(t)

    # -- public API --

    def request(self, item_id: str, source_path: str, on_ready):
        """
        Schedule a debounced load. `on_ready(item_id, Gdk.Texture)` is
        called on the GLib main thread once decoding finishes.
        """
        self.cancel(item_id)  # clear any prior pending timeout for this item

        def fire_after_debounce():
            self._pending_timeouts.pop(item_id, None)
            self._live[item_id] = True
            self._job_queue.put((item_id, source_path, on_ready))
            return GLib.SOURCE_REMOVE

        timeout_id = GLib.timeout_add(DEBOUNCE_MS, fire_after_debounce)
        self._pending_timeouts[item_id] = timeout_id

    def cancel(self, item_id: str):
        """Call when an item scrolls out of view before its debounce fires."""
        timeout_id = self._pending_timeouts.pop(item_id, None)
        if timeout_id is not None:
            GLib.source_remove(timeout_id)
        # A job already sitting in the queue or mid-decode is left to
        # finish (cheap, bounded by the worker pool size) but the worker
        # checks `_live` before doing any real work and before delivering,
        # so a cancelled job's result is simply dropped.
        self._live.pop(item_id, None)

    # -- internal --

    def _cache_path(self, source_path: str) -> str:
        try:
            mtime = os.path.getmtime(source_path)
        except OSError:
            mtime = 0
        # thumb_size is part of the key so a loader using a larger size
        # never silently reuses a smaller cached file (or vice versa).
        key = f"{source_path}:{mtime}:{self._thumb_size}"
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return os.path.join(CACHE_DIR, f"{digest}.{self._cache_ext}")

    def _worker_loop(self):
        """Long-lived worker: pulls jobs off the shared queue one at a
        time, forever. Exactly `max_concurrent` of these exist per loader
        instance, so this is the whole story of the thread-count cap — no
        per-request thread spawning anywhere."""
        while True:
            item_id, source_path, on_ready = self._job_queue.get()
            try:
                if not self._live.get(item_id):
                    continue  # cancelled before a worker got to it

                cache_path = self._cache_path(source_path)
                try:
                    if os.path.exists(cache_path):
                        pixbuf = GdkPixbuf.Pixbuf.new_from_file(cache_path)
                    else:
                        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                            source_path, self._thumb_size, -1, True
                        )
                        try:
                            pixbuf.savev(cache_path, self._cache_ext, [], [])
                        except GLib.Error:
                            pass  # cache write failure is non-fatal
                except GLib.Error:
                    continue

                if not self._live.get(item_id):
                    continue  # cancelled mid-decode; drop result

                # Hand off to the main thread for GTK/Gdk object creation
                GLib.idle_add(self._deliver, item_id, pixbuf, on_ready)
            finally:
                self._job_queue.task_done()

    def _deliver(self, item_id, pixbuf, on_ready):
        self._live.pop(item_id, None)
        texture = Gdk.Texture.new_for_pixbuf(pixbuf)
        on_ready(item_id, texture)
        return GLib.SOURCE_REMOVE
