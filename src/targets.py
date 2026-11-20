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


def supported_targets(background_keys=(), screensaver_keys=(), portal_set_on_support=False):
    """Return the targets this desktop can actually apply.

    A lock-screen target needs either a screensaver picture setting or a
    portal that understands ``set-on``. Desktop always works through the
    existing background setter.
    """
    keys = set(background_keys or ())
    lock_keys = set(screensaver_keys or ())
    desktop = bool(keys & {"picture-uri", "picture-uri-dark"})
    lock = "picture-uri" in lock_keys
    if portal_set_on_support:
        desktop = True
        lock = True
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


def screensaver_keys_for_target(target: str) -> tuple[str, ...]:
    """Return the GNOME screensaver keys to write for a target."""
    return ("picture-uri",) if target in ("lock", "both") else ()
