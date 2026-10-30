# Wallmat

A keyboard-friendly wallpaper chooser built with **GTK 4** and **libadwaita**. Browse wallpapers in eight layouts, organize favorites, preview images, and optionally generate desktop colors with [Matugen](https://github.com/InioX/matugen).

<p align="center">
  <img src="screenshots/split_screen.png" alt="Wallmat Split-Screen Preview" width="720">
</p>

<p align="center">
  <a href="LICENSE"><img alt="License: GPL-3.0-only" src="https://img.shields.io/badge/license-GPL--3.0--only-blue.svg"></a>
  <img alt="GTK 4" src="https://img.shields.io/badge/GTK-4-4a86cf">
  <img alt="Python" src="https://img.shields.io/badge/Python-3-3776ab">
</p>

## Layouts

<p align="center">
  <img src="screenshots/stacked_deck.png" alt="Stacked Deck" width="24%">
  <img src="screenshots/infinite_ribbon.png" alt="Infinite Ribbon" width="24%">
  <img src="screenshots/masonry_grid.png" alt="Masonry Grid" width="24%">
  <img src="screenshots/glassmorphism.png" alt="Glassmorphism" width="24%">
</p>
<p align="center">
  <img src="screenshots/parallax_gallery.png" alt="Parallax Gallery" width="24%">
  <img src="screenshots/radial_fan.png" alt="Radial Fan" width="24%">
  <img src="screenshots/cylindrical_ring.png" alt="Cylindrical Ring" width="24%">
  <img src="screenshots/split_screen.png" alt="Split-Screen Preview" width="24%">
</p>

| Layout | Experience |
|---|---|
| Split-Screen Preview | Compare a wallpaper with a large preview |
| Stacked Deck | Browse a layered stack |
| Infinite Ribbon | Move through a continuous horizontal strip |
| Masonry Grid | Explore a virtualized thumbnail grid |
| Glassmorphism | Browse translucent layered cards |
| Parallax Gallery | Explore a depth-inspired gallery |
| Radial Fan | Browse cards arranged around a focus |
| Cylindrical Ring | Rotate a carousel with a 3D-style effect |

## Quick start

On Debian or Ubuntu, install the runtime dependencies:

```sh
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1
# Optional WebP support
sudo apt install webp-pixbuf-loader
```

On Fedora, use the equivalent packages with `dnf`:

```sh
sudo dnf install python3-gobject gtk4 libadwaita
# Optional WebP support
sudo dnf install webp-pixbuf-loader
```

Run from a source checkout:

```sh
python3 src/main.py ~/Pictures/Wallpapers
```

Wallmat defaults to `/usr/share/backgrounds` when no folder is supplied. Choose a layout at launch with:

```sh
python3 src/main.py ~/Pictures/Wallpapers --layout infinite_ribbon
```

## Highlights

- Search, favorites, recent wallpapers, and sorting.
- Full-screen preview with zoom and pan.
- Apply wallpapers directly or run Matugen with custom arguments.
- Auto-rotation, random selection, and applied-wallpaper history.
- Keyboard navigation, drag-and-drop folder switching, and persistent preferences.

See **[Controls and features](docs/FEATURES.md)** for usage details and **[Configuration](docs/CONFIGURATION.md)** for supported formats, cache behavior, scan settings, and preference persistence.

## Matugen and command-line mode

Wallmat can provide a selected path to scripts:

```sh
WP="$(python3 src/main.py ~/Pictures/Wallpapers --plain 2>/dev/null)"
matugen image "$WP" --type scheme-smart --mode dark
```

In normal UI mode, **Set as wallpaper** updates GNOME's background settings. **Apply wallpaper + Matugen** also runs Matugen. Customize its arguments with `--matugen-args`; see the [Matugen and CLI guide](docs/FEATURES.md#matugen-and-cli-mode).

## Favorites

Favorites are stored in `~/.config/wallmat/favorites.json` and exported to `favorites.txt` in the same directory. Invalid favorites data is preserved in a recovery backup rather than silently overwritten.

## License

Wallmat is licensed under **GPL-3.0-only**. See [LICENSE](LICENSE).
