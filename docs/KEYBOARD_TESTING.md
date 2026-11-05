# Keyboard navigation test plan

This is a manual GTK-session test plan for issue #64. It records what to
exercise without treating source-code inspection as proof that focus behavior
works in a running desktop.

## Test setup

1. Use a folder containing at least five supported wallpapers so navigation
   boundaries and selection changes are observable.
2. Start Wallmat normally, then repeat with each layout:
   `python3 src/main.py /path/to/wallpapers --layout LAYOUT_ID`.
3. Use a keyboard only for the interaction checks. Repeat with a pointer to
   confirm click behavior remains available.
4. Record the GTK version, desktop/session, layout, and any failure. Do not
   mark a layout passed if it was not tested.

## Per-layout checks

Run the following for all eight layout IDs:

- [ ] `split_screen` — Left/Right moves the carousel focus; focus stops at
  either end; Enter selects the focused wallpaper.
- [ ] `stacked_deck` — Left/Right deals the previous/next card; Enter selects
  the front card. Check that keys pressed during the deal do not lose focus.
- [ ] `infinite_ribbon` — Left/Right continues through the ribbon; Enter
  selects the focused card. Check navigation across the repeated-copy seam.
- [ ] `masonry_grid` — GTK GridView receives keyboard focus; arrow navigation
  moves through the grid; Enter activation selects the intended item. Check
  both row and column transitions.
- [ ] `glassmorphism` — Left/Right moves focus without selecting; Enter
  commits the focused card.
- [ ] `parallax_gallery` — Left/Right moves the foreground focus without
  selecting; Enter commits the focused card.
- [ ] `radial_fan` — Left/Right rotates the front card; Enter selects it.
- [ ] `cylindrical_ring` — Left/Right centers the previous/next card; Enter
  selects the centered card.

For every layout, also check:

- [ ] Focus is visible and remains on a meaningful control after selection.
- [ ] The selected wallpaper is not changed merely by moving focus with arrows.
- [ ] Navigation remains usable with an empty folder and with one wallpaper.
- [ ] Tab and Shift+Tab can leave the wallpaper view and reach the surrounding
  controls in a predictable order; focus never becomes trapped.
- [ ] After switching layouts and switching back, keyboard focus remains
  usable and no stale item is activated.

## Global shortcuts

- [ ] Ctrl+F reveals the filter and moves keyboard focus into it.
- [ ] Ctrl+O opens the folder chooser; Escape/cancel leaves the current folder
  unchanged.
- [ ] Escape clears and hides a visible filter; a second Escape closes Wallmat.
- [ ] `?` and the Shortcuts button open the shortcut help dialog.
- [ ] The shortcut dialog can be dismissed with its close action and focus
  returns to a usable part of the window.

## Reporting

Record each layout as **Pass**, **Fail**, or **Not tested**. For failures,
include the exact key sequence, expected result, actual result, GTK version,
desktop/session, and whether the issue reproduces after restarting Wallmat.

This checklist is a test procedure, not evidence of a passing runtime test.
Screen-reader names, roles, and selected/favorite announcements are covered by
the separate accessibility work in issues #54 and #67.
