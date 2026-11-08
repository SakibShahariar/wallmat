# Wallmat

A GTK4 / libadwaita wallpaper chooser for Linux, featuring eight layouts, favorites, collections, full-screen previews, and optional [Matugen](https://github.com/InioX/matugen) theming.

<p align="center">
  <img src="screenshots/split_screen.png" alt="Wallmat split-screen preview" width="720">
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

| Layout | Style |
|---|---|
| Split-Screen | Large side-by-side preview |
| Stacked Deck | Layered cards |
| Infinite Ribbon | Continuous horizontal strip |
| Masonry Grid | Virtualized thumbnail grid |
| Glassmorphism | Translucent cards |
| Parallax Gallery | Depth effect |
| Radial Fan | Radial card arrangement |
| Cylindrical Ring | 3D-style carousel |

## Features

- Search, sorting, tags, and drag-and-drop folder switching
- Favorites, collections, recent wallpapers, and batch actions
- Full-screen preview with zoom and pan
- Wallpaper application through XDG Wallpaper portal / GNOME integration
- Optional Matugen color generation and preview
- Timed rotation, random selection, and wallpaper history
- Keyboard navigation, backup, and restore

## Installation

**Debian / Ubuntu**
```sh
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1
```

**Fedora**
```sh
sudo dnf install python3-gobject gtk4 libadwaita
```

Run from the source directory:

```sh
python3 src/main.py ~/Pictures/Wallpapers
```

Default folder: `/usr/share/backgrounds`.

Choose a layout with `--layout`:

```sh
python3 src/main.py ~/Pictures/Wallpapers --layout infinite_ribbon
```

Optional WebP support: install `webp-pixbuf-loader`.

## Matugen and CLI

Use the selected wallpaper path in scripts:

```sh
WP="$(python3 src/main.py ~/Pictures/Wallpapers --plain 2>/dev/null)"
matugen image "$WP" --type scheme-smart --mode dark
```

The **Apply wallpaper + Matugen** action combines both steps. Customize Matugen arguments with `--matugen-args`.

On Wayland, wallpaper changes use the XDG Wallpaper portal. GNOME settings are used as a fallback when the portal is unavailable.

## Documentation

- [Features and controls](docs/FEATURES.md)
- [Configuration and supported formats](docs/CONFIGURATION.md)
- [Screenshot coverage](docs/SCREENSHOTS.md)

## License

[GPL-3.0-only](LICENSE)
