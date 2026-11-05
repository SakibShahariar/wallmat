# Batch selection and actions test plan

The batch-selection dialog is available from **More → Batch actions → Select
multiple…**. It operates on the currently visible/filtered wallpaper results,
independently of the active gallery layout.

## Runtime checks

- [ ] Open the dialog from each of the eight layouts.
- [ ] Verify the list contains the current visible results, including the
  effects of text search, favorites-only, and tag filtering.
- [ ] Select multiple non-adjacent rows using GTK's modifier-key selection.
- [ ] Select a contiguous range using GTK's range-selection behavior.
- [ ] Favorite several selected wallpapers and verify they persist after
  restarting Wallmat.
- [ ] Remove several selected wallpapers from favorites and verify the
  favorites-only view refreshes correctly.
- [ ] Add several selected wallpapers to a named collection and verify the
  collection contents after switching away and back.
- [ ] Export selected paths to a text file and verify one absolute path per
  line. This exports a path list; it does not copy the image files.
- [ ] Verify empty selection, duplicate collection membership, write errors,
  and cancelling the export dialog are handled without losing current data.
- [ ] Verify the main layout selection is not changed merely by opening or
  closing the batch dialog.

## Reporting

Record the active layout, filters, selected row count, operation, and outcome.
The dialog's presence is not proof of correct GTK multi-selection behavior;
complete these checks in a running desktop before closing issue #36.
