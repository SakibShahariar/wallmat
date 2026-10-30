# Controls and features

## Browsing

- **← / →** — move focus in layouts that support keyboard navigation.
- **Enter** — select the focused wallpaper where supported.
- **Click** — select a wallpaper. Stacked Deck and some interactive layouts have different selection behavior.
- **Ctrl + F** — filter by filename or folder path.
- **Favorites only** — combine the favorites filter with text search (normal UI mode).
- **Sort** — name, modification date, largest resolution, random order, or immediate-subfolder grouping. Search and favorites filters preserve the selected order.
- **Recent wallpapers** — reopen up to eight recently applied wallpapers from the current folder. Missing or out-of-folder items do not change the selection.
- **Surprise me** — apply a random wallpaper from the filtered results, avoiding the configured recent-history window until the candidate pool is exhausted.

## Applying and previewing

- **More menu** — contains auto-rotation and its interval, Previous/Next, Clear history, Export favorites, and Remove missing favorites. Primary wallpaper actions remain visible beside the layout controls.

- **Set as wallpaper** — update GNOME's background settings.
- **Apply wallpaper + Matugen** — apply the wallpaper and run Matugen.
- **Auto-rotate** — rotate every 1, 5, 10, or 30 minutes. Rotation stops when Wallmat closes.
- **Previous** — reapply an earlier wallpaper from saved applied history.
- **Next** — choose another random wallpaper.
- **Clear history** — clear saved applied history and the Recent list.
- **Preview** — open the selected image full-screen, zoom, and scroll to pan.
- **Light/dark preview context** — compare contrast without changing GNOME's theme or wallpaper.
- **Click metadata** — selected image details include dimensions, format, aspect ratio, file size, modification time, and path. Details load off the UI thread and can be copied or hidden.

## Folders and shortcuts

- **Folder menu → Choose wallpaper folder / Ctrl + O** — open a local folder picker, then confirm before replacing the collection. The last chosen folder is restored on the next normal UI launch when no directory is supplied on the command line.
- **Drag and drop** — drop a local folder onto the window and confirm before replacing the collection. Invalid drops leave the current folder unchanged.
- **Escape** — clear the filter, or close the window when the filter is hidden.
- **? / Shortcuts** — open the keyboard shortcut cheatsheet.
- Use the layout selector at the bottom of the window to switch layouts without restarting.

Exact controls vary by layout. Wallpaper action buttons wrap onto additional rows when the window is too narrow.

## Matugen and CLI mode

Matugen must be installed to use its action. Customize its arguments without invoking a shell:

```sh
python3 src/main.py ~/Pictures/Wallpapers \
  --matugen-args="--type scheme-tonal-spot --mode light"
```

In `--plain` mode, Wallmat prints only the selected absolute wallpaper path to stdout; diagnostics go to stderr. Exit statuses are: `0` success, `2` user cancellation, `3` invalid or unreadable directory, and `4` scan failure or no supported wallpapers. Wallmat does not run Matugen in this mode, so Matugen failures belong to the calling shell command, not Wallmat's picker status.
