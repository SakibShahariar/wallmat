# wallmat

A GTK4 / libadwaita wallpaper chooser with **8 card-based layouts**, each with
a full keyboard interaction model: arrows move a visual **focus** ring,
Enter/click commits the **selection**. Built to sit in front of
[matugen](https://github.com/InioX/matugen) — pick a wallpaper, and the
pipeline re-themes your whole desktop from its colors (Material You).

## Contents

[Layouts](#layouts) · [Screenshots](#screenshots) · [Run](#run) · [matugen integration](#matugen-integration---plain) · [Theming note](#theming-note) · [Requirements](#requirements)

## Layouts

| Id | Display name | Tier |
| --- | --- | --- |
| `split_screen` | Split-Screen Preview | fast |
| `stacked_deck` | Stacked Deck | fast |
| `infinite_ribbon` | Infinite Ribbon | fast |
| `masonry_grid` | Masonry Grid | medium |
| `glassmorphism` | Glassmorphism | medium |
| `parallax_gallery` | Parallax Gallery | medium |
| `radial_fan` | Radial Fan | slow |
| `cylindrical_ring` | Cylindrical Ring | slow |

## Screenshots

| | | | |
|---|---|---|---|
| ![Split-Screen Preview](screenshots/split_screen.png) | ![Stacked Deck](screenshots/stacked_deck.png) | ![Infinite Ribbon](screenshots/infinite_ribbon.png) | ![Masonry Grid](screenshots/masonry_grid.png) |
| ![Glassmorphism](screenshots/glassmorphism.png) | ![Parallax Gallery](screenshots/parallax_gallery.png) | ![Radial Fan](screenshots/radial_fan.png) | ![Cylindrical Ring](screenshots/cylindrical_ring.png) |

## Run

```bash
python3 src/main.py /path/to/wallpaper/folder
python3 src/main.py /path/to/wallpaper/folder --layout infinite_ribbon
```

- Defaults to `/usr/share/backgrounds` if no folder is given.
- There's no header bar and no in-app UI for switching layouts —
  `--layout` at the command line is the only way to pick one for a given
  launch. The window still remembers the last layout you launched into
  via GSettings, it's just not user-switchable at runtime without
  relaunching.
- `--layout` launches directly into that layout and sizes the window for it.
- Press **Escape** to close — there's no title bar, so this is the only
  way to close the window from the keyboard (no minimize/maximize either).

### Remembering the last layout

Wallmat uses the GSettings schema in `data/dev.sakib.Wallmat.gschema.xml`.
For a local checkout, compile and install it for your user before launching
if you want the selected layout to persist across restarts:

```sh
mkdir -p ~/.local/share/glib-2.0/schemas
cp data/dev.sakib.Wallmat.gschema.xml ~/.local/share/glib-2.0/schemas/
glib-compile-schemas ~/.local/share/glib-2.0/schemas/
```

If the schema is not installed, Wallmat falls back to an in-memory preference.

### Keyboard and pointer behavior

Most layouts use the shared contract below, but a few deliberately differ.
These exceptions are listed explicitly so the on-screen hints and actual
interaction are predictable.

For layouts using the shared contract:

- **← / →** — move focus only and show the focus ring; they do not commit
  a wallpaper selection
- **Enter** — commit the focused wallpaper
- **click** — select the clicked wallpaper

| Layout | Browse / focus | Select / activate | Exception |
| --- | --- | --- | --- |
| Stacked Deck | ← / → deals the deck; swipe also deals | Enter or the Select button chooses the front card | Click/swipe advances the deck instead of selecting |
| Masonry Grid | Scroll the grid | Click a wallpaper | Keyboard arrows and Enter are not supported |
| Radial Fan | ← / → or mouse wheel / touchpad scroll cycles the front card | Enter selects the front card; click selects the hit card | Scrolling changes the front card directly |
| Cylindrical Ring | ← / → or scroll rotates the ring | Enter commits the front card; click selects the card under the pointer | Scroll changes focus, not selection |
| Infinite Ribbon | ← / → moves keyboard focus; scrolling moves the ribbon | Enter or click selects | Scroll position and keyboard focus are separate |

## matugen integration (`--plain`)

Full pipeline mode that makes the app a drop-in replacement for the old
`wallpicker.py`:

```bash
WP=$(python3 src/main.py /mnt/Storage/Wallpapers --plain 2>/dev/null | string trim)
matugen image "$WP" --type scheme-smart --mode dark
gsettings set org.gnome.desktop.background picture-uri "file://$WP"
```

`--plain` silences every feedback line; on selection the app prints the bare
wallpaper path to stdout (the *only* stdout line) and exits. The reference
fish pipeline lives in `dotfiles/Scripts/Scripts/matugen.fish`.

## Theming note

Selection/focus ring colors resolve the active theme's
`theme_selected_bg_color` at runtime (via style contexts), so the chooser
follows your installed GNOME theme + matugen output instead of a hardcoded
accent.

## Requirements

```bash
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1
# optional WebP thumbnails:
sudo apt install webp-pixbuf-loader
```