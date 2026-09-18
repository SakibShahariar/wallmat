# material-picker

A GTK4 / libadwaita wallpaper chooser with **8 card-based layouts**, each with
a full keyboard interaction model: arrows move a visual **focus** ring,
Enter/click commits the **selection**. Built to sit in front of
[matugen](https://github.com/InioX/matugen) — pick a wallpaper, and the
pipeline re-themes your whole desktop from its colors (Material You).

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

### Keyboard contract

Every layout follows the same rules (verify with any wallpaper folder):

- **← / →** — move focus only, draws the focus ring, prints nothing
  visible in normal usage; commit stays with the next step
- **Enter** — commit the focused card (the selection border)
- **click** — also selects (the card that's currently focused committed)

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

## Keyboard-driven behavior

See `src/layouts/*.py`: the deck/ring/fan/glass/parallax layouts intercept
keys in CAPTURE phase on their own views so GTK's built-in list navigation
never turns arrows into commits (see `src/layouts/split_screen.py` for the
canonical comment).