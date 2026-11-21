"""Wallpaper target capability detection and routing (issue #76).

Kept free of GTK/Gio imports so the rules can be unit-tested in CI. The
portal and GSettings backends provide the observed capabilities; this module
decides what can be offered and how a requested target is expressed.
"""

TARGETS = ("desktop", "lock", "both")

TARGET_LABELS = {
    "desktop": "Desktop background",
    "lock": "Lock screen",
    "both": "Desktop + lock screen",
}

# Values accepted by org.freedesktop.portal.Wallpaper's ``set-on`` option.
PORTAL_SET_ON = {
    "desktop": "background",
    "lock": "lockscreen",
    "both": "both",
}


def portal_set_on(target: str) -> str | None:
    """Return the portal ``set-on`` value for a target, if there is one."""
    return PORTAL_SET_ON.get(target)


# GNOME 40+ unified the lock screen with the desktop: GNOME Shell builds its
# lock-screen background from org.gnome.desktop.background and ignores the
# screensaver picture-uri key, so a separate lock-screen wallpaper is not
# possible there even though the key still exists in the schema.
GNOME_NO_SEPARATE_LOCK_MAJOR = 40


def gnome_has_separate_lock_screen(shell_version=None):
    """Return whether this GNOME Shell supports a separate lock wallpaper.

    ``shell_version`` is the string from the org.gnome.Shell D-Bus
    ShellVersion property (e.g. "51.1"). ``None``/non-GNOME means unknown,
    in which case we fall back to the schema/portal checks.
    """
    if not shell_version:
        return None
    try:
        major = int(str(shell_version).split(".", 1)[0])
    except (TypeError, ValueError):
        return None
    return major < GNOME_NO_SEPARATE_LOCK_MAJOR


def supported_targets(background_keys=(), screensaver_keys=(),
                      portal_set_on_support=False, gnome_shell_version=None):
    """Return the targets this desktop can actually apply.

    Desktop always works through the existing background setter. A lock
    target needs a working separate lock-screen setting: either a real
    screensaver picture key, or a portal that honours ``set-on``. On GNOME
    40+ neither applies — the lock screen reuses the desktop wallpaper — so
    only the desktop target is offered.
    """
    keys = set(background_keys or ())
    lock_keys = set(screensaver_keys or ())
    desktop = bool(keys & {"picture-uri", "picture-uri-dark"})
    lock = "picture-uri" in lock_keys
    if portal_set_on_support:
        desktop = True
        lock = True
    # GNOME 40+ ignored the screensaver picture key for the lock screen.
    if gnome_has_separate_lock_screen(gnome_shell_version) is False:
        lock = False
    supported = set()
    if desktop:
        supported.add("desktop")
    if lock:
        supported.add("lock")
        if desktop:
            supported.add("both")
    return supported


def resolve_target(requested, supported):
    """Return a safe target for this desktop.

    ``None`` means the requested target is unsupported and the caller must
    explain it instead of silently redirecting. An unknown or empty request
    falls back to desktop, preserving the previous default behavior.
    """
    if requested not in TARGETS:
        return "desktop" if "desktop" in set(supported) else None
    return requested if requested in set(supported) else None


def gnome_shell_version():
    """Return GNOME Shell's version string over D-Bus, or None if unavailable.

    This function imports Gio lazily so the pure rules above stay testable
    in the dependency-light CI job.
    """
    import gi
    gi.require_version("Gio", "2.0")
    from gi.repository import Gio
    try:
        proxy = Gio.DBusProxy.new_for_bus_sync(
            Gio.BusType.SESSION, Gio.DBusProxyFlags.NONE, None,
            "org.gnome.Shell", "/org/gnome/Shell", "org.gnome.Shell", None,
        )
        return proxy.get_cached_property("ShellVersion").get_string()
    except Exception:
        return None


def screensaver_keys_for_target(target: str) -> tuple[str, ...]:
    """Return the GNOME screensaver keys to write for a target."""
    return ("picture-uri",) if target in ("lock", "both") else ()
