# Screenshot coverage and refresh guide

The README currently includes a gallery for all eight wallpaper layouts. The
images are useful as a visual overview, but their presence alone does not prove
that they still match the current UI.

## Current inventory

| UI surface | Asset | Audit note |
|---|---|---|
| Split-Screen Preview | `screenshots/split_screen.png` | Present; not revalidated in a live GTK session |
| Stacked Deck | `screenshots/stacked_deck.png` | Present; image inspected, appears to show the deck and selection action |
| Infinite Ribbon | `screenshots/infinite_ribbon.png` | Present; not revalidated in a live GTK session |
| Masonry Grid | `screenshots/masonry_grid.png` | Present; not revalidated in a live GTK session |
| Glassmorphism | `screenshots/glassmorphism.png` | Present; image inspected, shows the horizontal card row |
| Parallax Gallery | `screenshots/parallax_gallery.png` | Present; not revalidated in a live GTK session |
| Radial Fan | `screenshots/radial_fan.png` | Present, but the available image appears mostly blank with cards clipped at the top; recapture after checking the layout |
| Cylindrical Ring | `screenshots/cylindrical_ring.png` | Present; image inspected, shows the centered card and adjacent cards |

The following workflow surfaces do not yet have dedicated README screenshots:

- Favorites and the Favorites-only filter.
- Folder chooser and the confirmation before switching folders.
- Scan progress and cancellation.
- Plain-mode terminal output (include only if a terminal example helps explain
  the command-line contract).

This inventory is a repository-asset audit, not a claim that the screenshots
have been verified against a current running build. The screenshots that could
not be inspected during this audit remain explicitly unverified.

## Refresh rule

When a change materially affects a layout or visible workflow:

1. Run Wallmat from the current source checkout in a GTK desktop session.
2. Use a representative folder with enough wallpapers to show navigation,
   selection, empty/loading states where relevant, and the actual layout.
3. Capture the UI after thumbnails and transitions have settled. Avoid partial
   loads, clipped content, pointer hover artifacts, and unrelated dialogs.
4. Replace the corresponding image in `screenshots/` and update its README
   alt text or description if the visible behavior changed.
5. Inspect the rendered image at README display size before committing it.
6. Record any surfaces that cannot be captured in the current environment
   instead of substituting mockups or claiming they were verified.

Screenshots must come from the real application. Do not create synthetic UI
images or use a mockup to imply a workflow exists.
