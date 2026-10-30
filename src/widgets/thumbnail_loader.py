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

from cache_utils import DEFAULT_CACHE_LIMIT_BYTES, prune_cache_directory


CACHE_DIR = os.path.expanduser("~/.cache/wallpaper-chooser/thumbs")
DEFAULT_THUMB_SIZE = 480
DEBOUNCE_MS = 100
POOL_SIZE = 3
MAX_QUEUED_JOBS = 128
CACHE_PRUNE_EVERY = 16
_CACHE_MAINTENANCE_LOCK = threading.Lock()


def webp_supported() -> bool:
    formats = GdkPixbuf.Pixbuf.get_formats()
    return any(
        fmt.get_name() == "webp"
        and not fmt.is_disabled()
        and fmt.is_writable()
        for fmt in formats
    )


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
        self._cache_writes = 0
        self._prune_cache()
        self._webp_ok = webp_supported()
        self._cache_ext = "webp" if self._webp_ok else "png"
        self._thumb_size = thumb_size

        # item_id -> GLib timeout source id, for pending debounced requests
        self._pending_timeouts: dict[str, int] = {}
        # item_id -> generation token for the current request. A boolean
        # is not sufficient: cancel + re-request can make an old queued
        # result look live again if the same item_id is reused.
        self._generation: dict[str, int] = {}
        # item_id -> generation token while queued/decoding/delivering.
        self._live: dict[str, int] = {}

        # Bound pending work as well as worker count. When a burst fills the
        # queue, the oldest not-yet-started request is discarded in favor of
        # the newest visible item.
        self._job_queue: "queue.Queue" = queue.Queue(maxsize=MAX_QUEUED_JOBS)
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
        self.cancel(item_id)  # invalidate any prior timeout/job/delivery
        generation = self._generation[item_id]

        def fire_after_debounce():
            self._pending_timeouts.pop(item_id, None)
            if self._generation.get(item_id) != generation:
                return GLib.SOURCE_REMOVE
            self._live[item_id] = generation
            self._enqueue_job((item_id, source_path, on_ready, generation))
            return GLib.SOURCE_REMOVE

        timeout_id = GLib.timeout_add(DEBOUNCE_MS, fire_after_debounce)
        self._pending_timeouts[item_id] = timeout_id

    def cancel(self, item_id: str):
        """Call when an item scrolls out of view before its debounce fires."""
        timeout_id = self._pending_timeouts.pop(item_id, None)
        if timeout_id is not None:
            GLib.source_remove(timeout_id)
        # Invalidate queued work and idle callbacks too. The generation
        # token prevents an old result from being accepted after the same
        # item_id has already been requested again.
        self._generation[item_id] = self._generation.get(item_id, 0) + 1
        self._live.pop(item_id, None)

    # -- internal --

    def _enqueue_job(self, job):
        try:
            self._job_queue.put_nowait(job)
            return
        except queue.Full:
            pass

        try:
            dropped = self._job_queue.get_nowait()
        except queue.Empty:
            dropped = None
        if dropped is not None:
            self._job_queue.task_done()
            dropped_id, _path, _callback, dropped_generation = dropped
            if self._live.get(dropped_id) == dropped_generation:
                self._live.pop(dropped_id, None)

        try:
            self._job_queue.put_nowait(job)
        except queue.Full:
            item_id, _path, _callback, generation = job
            if self._live.get(item_id) == generation:
                self._live.pop(item_id, None)

    def _prune_cache(self):
        with _CACHE_MAINTENANCE_LOCK:
            prune_cache_directory(CACHE_DIR, DEFAULT_CACHE_LIMIT_BYTES)

    def _note_cache_write(self):
        self._cache_writes += 1
        if self._cache_writes % CACHE_PRUNE_EVERY == 0:
            self._prune_cache()

    def _cache_path(self, source_path: str) -> str:
        try:
            stat = os.stat(source_path)
            modified_ns = stat.st_mtime_ns
            size = stat.st_size
        except OSError:
            modified_ns = 0
            size = 0
        # Size and nanosecond mtime invalidate stale thumbnails even when
        # a file is replaced while retaining a coarse timestamp.
        key = f"{source_path}:{modified_ns}:{size}:{self._thumb_size}"
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return os.path.join(CACHE_DIR, f"{digest}.{self._cache_ext}")

    def _worker_loop(self):
        """Long-lived worker: pulls jobs off the shared queue one at a
        time, forever. Exactly `max_concurrent` of these exist per loader
        instance, so this is the whole story of the thread-count cap — no
        per-request thread spawning anywhere."""
        while True:
            item_id, source_path, on_ready, generation = self._job_queue.get()
            try:
                if (self._live.get(item_id) != generation
                        or self._generation.get(item_id) != generation):
                    continue  # superseded before a worker got to it

                cache_path = self._cache_path(source_path)
                try:
                    if os.path.exists(cache_path):
                        try:
                            pixbuf = GdkPixbuf.Pixbuf.new_from_file(cache_path)
                            try:
                                os.utime(cache_path, None)
                            except OSError:
                                pass
                        except GLib.Error:
                            # A truncated/corrupt cache must not permanently
                            # hide a valid source image on later launches.
                            try:
                                os.remove(cache_path)
                            except OSError:
                                pass
                            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                                source_path, self._thumb_size, -1, True
                            )
                            try:
                                pixbuf.savev(cache_path, self._cache_ext, [], [])
                                self._note_cache_write()
                            except GLib.Error:
                                pass  # cache write failure is non-fatal
                    else:
                        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(
                            source_path, self._thumb_size, -1, True
                        )
                        try:
                            pixbuf.savev(cache_path, self._cache_ext, [], [])
                            self._note_cache_write()
                        except GLib.Error:
                            pass  # cache write failure is non-fatal
                except GLib.Error:
                    continue

                if (self._live.get(item_id) != generation
                        or self._generation.get(item_id) != generation):
                    continue  # cancelled/superseded mid-decode

                # The main-thread delivery rechecks generation as cancel()
                # can run after idle_add() but before this callback executes.
                GLib.idle_add(self._deliver, item_id, generation, pixbuf, on_ready)
            finally:
                self._job_queue.task_done()

    def _deliver(self, item_id, generation, pixbuf, on_ready):
        if (self._live.get(item_id) != generation
                or self._generation.get(item_id) != generation):
            return GLib.SOURCE_REMOVE
        self._live.pop(item_id, None)
        texture = Gdk.Texture.new_for_pixbuf(pixbuf)
        on_ready(item_id, texture)
        return GLib.SOURCE_REMOVE
