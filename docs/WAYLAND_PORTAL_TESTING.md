# Wayland wallpaper portal test plan

Wallmat uses the XDG Wallpaper portal on Wayland sessions. The request uses
`SetWallpaperFile` with a read-only file descriptor, asks the portal to show a
preview, and targets the desktop background. It does not use a local `file://`
URI with `SetWallpaperURI`.

If the portal service or Wallpaper method is unavailable, Wallmat falls back
to its existing GNOME GSettings wallpaper setter. A portal cancellation or
reported failure is surfaced to the user and is not silently bypassed with a
direct settings write.

## Runtime checks

- [ ] On GNOME Wayland with a Wallpaper-capable portal backend, choose a
  wallpaper and verify that the portal preview/confirmation appears.
- [ ] Approve the request and verify that the wallpaper changes.
- [ ] Verify that applied-wallpaper history and recent paths update only after
  a successful portal response.
- [ ] Cancel the portal request and verify that the existing wallpaper stays
  unchanged and no direct GSettings fallback is attempted.
- [ ] Trigger a portal error/denial and verify that Wallmat reports it without
  bypassing the portal decision.
- [ ] Run with the portal service unavailable and verify that the existing
  GNOME GSettings method is attempted.
- [ ] Run with the Wallpaper interface/method unavailable and verify the same
  fallback behavior.
- [ ] On an X11 session, verify that the existing GSettings path is used
  directly without a portal prompt.
- [ ] Verify that the window remains responsive while the portal request is
  waiting for user interaction.
- [ ] Repeat in another desktop environment that provides the standard
  Wallpaper portal, recording its portal/backend versions.

## Reporting

Record the desktop/session, portal frontend/backend, GTK version, Wallmat
commit, response outcome, and whether the request used the portal or fallback.
A successful source-level D-Bus request is not proof that every compositor
backend implements the Wallpaper portal.
