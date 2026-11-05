# Screen-reader and keyboard accessibility test plan

This checklist covers the custom wallpaper cards and browsing controls tracked
by issue #67. Accessible labels in source code are not proof that Orca announces
them correctly; run these checks in a real GTK desktop session before marking
the issue complete.

## Test setup

1. Use a current Wallmat build with at least five wallpapers, including two
   files with the same basename in different subfolders if possible.
2. Start Orca and launch Wallmat in a normal desktop session.
3. Record the GTK version, desktop/session, Orca version, and Wallmat commit.
4. Repeat the checks in each of the eight layouts.

## Per-layout checks

- [ ] Split-Screen Preview — each visible card is announced by its wallpaper
  filename; the selected card is distinguishable.
- [ ] Stacked Deck — the deck is announced as a named wallpaper browser; its
  current keyboard-focus filename and browse/select instructions are exposed.
- [ ] Infinite Ribbon — each visible card is announced by its wallpaper
  filename; focus and selection are distinguishable.
- [ ] Masonry Grid — each image card has a filename label and selected state.
- [ ] Glassmorphism — each picture has a filename label and selected state.
- [ ] Parallax Gallery — foreground pictures have filename labels; keyboard
  focus and committed selection are distinguishable.
- [ ] Radial Fan — the group exposes the focused and selected wallpaper names
  plus Left/Right and Enter instructions.
- [ ] Cylindrical Ring — the group exposes the focused and selected wallpaper
  names plus Left/Right and Enter instructions.

## Favorite and core workflow checks

- [ ] The favorite control announces **Add to favorites** when the selected
  wallpaper is not a favorite.
- [ ] After favoriting, the control announces **Remove favorite**; removing it
  changes the label back.
- [ ] The Tag dropdown, Collection dropdown, filter entry, layout selector,
  folder chooser, and backup/restore actions have useful accessible names.
- [ ] Arrow keys move focus without committing a wallpaper where the layout
  separates focus from selection.
- [ ] Enter commits the focused wallpaper and the screen reader can identify
  the resulting selection.
- [ ] Tab and Shift+Tab leave each wallpaper view predictably; no focus trap
  prevents access to surrounding controls.
- [ ] No custom-drawn card or browser group is exposed as an unlabeled graphic.

## High contrast and large text

- [ ] Enable the desktop's high-contrast setting and verify Glassmorphism cards
  no longer rely on low-opacity dimming; active and keyboard-focused cards
  retain clearly visible borders.
- [ ] Toggle high contrast while Wallmat is open and verify the Glassmorphism
  styling updates without restarting the app.
- [ ] Increase the desktop text scale substantially and verify labels, buttons,
  dialogs, dropdowns, and keyboard hints remain readable and are not clipped.
- [ ] Repeat the large-text check with long filenames and collection names.

## Reporting

For each failure, record the layout, exact key sequence, expected announcement,
actual announcement, selected wallpaper, and whether it reproduces after
restarting Wallmat. Mark each item **Pass**, **Fail**, or **Not tested**.

Do not mark this issue complete based only on source inspection or this
checklist's existence. A real Orca/GTK run is required.
