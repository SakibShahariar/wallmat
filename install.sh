#!/usr/bin/env bash
# Install Wallmat's launcher, icon and GSettings schema for the current user.
# Usage: ./install.sh [--uninstall]
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
BIN_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
APPLICATIONS="$DATA_HOME/applications"
ICONS="$DATA_HOME/icons/hicolor/scalable/apps"
SCHEMAS="$DATA_HOME/glib-2.0/schemas"
AUTOSTART="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"

uninstall() {
    rm -f "$APPLICATIONS/dev.sakib.Wallmat.desktop" \
          "$APPLICATIONS/dev.sakib.Wallmat.Settings.desktop" \
          "$ICONS/dev.sakib.Wallmat.svg" \
          "$AUTOSTART/dev.sakib.Wallmat.Schedule.desktop"
    if [ -f "$SCHEMAS/dev.sakib.Wallmat.gschema.xml" ]; then
        rm -f "$SCHEMAS/dev.sakib.Wallmat.gschema.xml"
        glib-compile-schemas "$SCHEMAS" 2>/dev/null || true
    fi
    command -v update-desktop-database >/dev/null 2>&1 && \
        update-desktop-database "$APPLICATIONS" 2>/dev/null || true
    echo "Wallmat launcher removed."
}

check_runtime() {
    command -v python3 >/dev/null 2>&1 || { echo "python3 is required" >&2; exit 1; }
    python3 - <<'PY' 2>/dev/null || {
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw
PY
        echo "GTK 4 and libadwaita (python3-gi / gir1.2-gtk-4.0 / gir1.2-adw-1) are required" >&2
        exit 1
    }
}

install() {
    check_runtime
    mkdir -p "$APPLICATIONS" "$ICONS" "$SCHEMAS" "$BIN_DIR" "$AUTOSTART"

    local main_exec="python3 $SOURCE_DIR/src/main.py"
    local settings_exec="python3 $SOURCE_DIR/src/settings.py"

    sed -e "s|@WALLMAT_EXEC@|$main_exec|g" \
        -e "s|@SETTINGS_EXEC@|$settings_exec|g" \
        "$SOURCE_DIR/data/dev.sakib.Wallmat.desktop" \
        > "$APPLICATIONS/dev.sakib.Wallmat.desktop"
    sed -e "s|@WALLMAT_EXEC@|$main_exec|g" \
        -e "s|@SETTINGS_EXEC@|$settings_exec|g" \
        "$SOURCE_DIR/data/dev.sakib.Wallmat.Settings.desktop" \
        > "$APPLICATIONS/dev.sakib.Wallmat.Settings.desktop"
    sed "s|@SCHEDULE_EXEC@|python3 $SOURCE_DIR/src/schedule_daemon.py|g" \
        "$SOURCE_DIR/data/dev.sakib.Wallmat.Schedule.desktop" \
        > "$AUTOSTART/dev.sakib.Wallmat.Schedule.desktop"
    cp "$SOURCE_DIR/data/dev.sakib.Wallmat.svg" "$ICONS/dev.sakib.Wallmat.svg"

    # A user-level hicolor directory needs its own index.theme before
    # gtk-update-icon-cache will build a cache for it; without a cache the
    # launcher falls back to image-missing.svg.
    if [ ! -f "$DATA_HOME/icons/hicolor/index.theme" ] \
            && [ -f /usr/share/icons/hicolor/index.theme ]; then
        cp /usr/share/icons/hicolor/index.theme "$DATA_HOME/icons/hicolor/index.theme"
    fi

    cp "$SOURCE_DIR/data/dev.sakib.Wallmat.gschema.xml" \
       "$SCHEMAS/dev.sakib.Wallmat.gschema.xml"
    glib-compile-schemas "$SCHEMAS"

    command -v update-desktop-database >/dev/null 2>&1 && \
        update-desktop-database "$APPLICATIONS" 2>/dev/null || true
    command -v gtk-update-icon-cache >/dev/null 2>&1 && \
        gtk-update-icon-cache -q -f "$DATA_HOME/icons/hicolor" 2>/dev/null || true

    echo "Wallmat installed for $(whoami)."
    echo "  Launcher: $APPLICATIONS/dev.sakib.Wallmat.desktop"
    echo "  Icon:     $ICONS/dev.sakib.Wallmat.svg"
    echo "  Settings: python3 $SOURCE_DIR/src/settings.py"
    echo "Restart your session (or log out/in) if the launcher does not appear immediately."
}

case "${1:-}" in
    --uninstall) uninstall ;;
    "") install ;;
    *) echo "Usage: $0 [--uninstall]" >&2; exit 2 ;;
esac
