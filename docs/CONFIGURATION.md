# Configuration

## Supported wallpaper formats

Wallmat scans PNG and JPEG images when their GdkPixbuf loaders are enabled. WebP is included only when the current session has an enabled WebP loader (for example, the optional `webp-pixbuf-loader` package on Debian/Ubuntu). Other formats are excluded because loader availability alone does not guarantee consistent GNOME desktop-background support.

## Thumbnail cache

Thumbnails are stored in `~/.cache/wallpaper-chooser/thumbs`. Decoding uses a fixed worker pool and a bounded pending queue. The disk cache is pruned to a 512 MiB limit. Cache keys include source file size and nanosecond modification time so changed images are regenerated.

## Directory scanning

Scanning is unlimited by default. Set `scan-depth` from 0 to 20; zero means unlimited and one means only the selected root directory. For example:

```sh
gsettings set dev.sakib.Wallmat scan-depth 2
```

Symlinked files and directories are skipped to avoid duplicate entries and directory cycles. The scanner also enforces a 10,000-wallpaper cap.

## Preferences and persistence

Wallmat can run without its GSettings schema, but preferences then last only for the current process. To enable persistence for your user account from a source checkout:

```sh
mkdir -p ~/.local/share/glib-2.0/schemas
cp data/dev.sakib.Wallmat.gschema.xml ~/.local/share/glib-2.0/schemas/
glib-compile-schemas ~/.local/share/glib-2.0/schemas/
```

Restart Wallmat after installing or updating the schema. If `glib-compile-schemas` is unavailable, install your distribution's GLib development utilities.

### Available settings

- `random-history-limit`: 0–20 recently selected wallpapers excluded from random selection; default 5. Set to 0 to disable the exclusion window.
- `scan-depth`: 0–20 directory depth; default 0 (unlimited).
- `applied-wallpaper-history`: up to 50 recently applied paths. Use the in-app **Clear history** action to clear it and the Recent list.

Favorites are stored in `~/.config/wallmat/favorites.json`. Wallpaper tags are stored separately in `~/.config/wallmat/tags.json`; assignments are relative to the selected folder where possible, while paths outside it remain absolute. Named wallpaper collections are stored in `~/.config/wallmat/collections.json` as ordered lists of absolute file paths. New saves use a versioned format with paths relative to the selected collection root; favorites outside that root remain absolute. When a collection has moved and its old favorite paths no longer exist, matching relative paths are resolved under the new root. Existing legacy arrays of absolute paths remain readable and are migrated the next time favorites are saved.

The app also persists layout, text filter, sort mode, Favorites only, last selection, recent wallpaper paths, and auto-rotate interval when the schema is installed. Selection is restored only when the file still exists in the current folder and matches the restored filters. Focus restoration is supported in Split-Screen Preview and selection restoration in Masonry Grid; other layouts and scroll position are not yet restored.


## Backup and restore

Use **More → Backup and restore** to export a versioned `wallmat-backup.json`
or restore one. Version-3 backups include favorites, per-wallpaper tags, named
collections, and the supported GSettings preferences: layout, filter, sorting, favorites-only
state, recent paths, wallpaper history, scan depth, and rotation settings.

Restore validates the backup format, version, favorites and tag paths,
preference names, types, and supported ranges before asking for confirmation.
The confirmation explains that included preferences, favorites, tags, and
collections will replace their current values. Wallmat does not include credentials or secrets in this
backup. Restart the application after a restore so all restored preferences
are reflected consistently.

Version-1 backups remain restorable and leave current tags and collections
untouched. Version-2 backups restore tags but leave current collections
untouched. Version-3 backups include all three data sections. Collections store absolute file paths; missing files are skipped
when a collection is opened, and files moved to another path must be added
again. Adding the current folder to a collection stores the wallpapers found
at that time; it is not a live folder link. If the
GSettings schema is unavailable, preference persistence remains unavailable;
install the schema as described above before relying on preferences surviving
a restart.
