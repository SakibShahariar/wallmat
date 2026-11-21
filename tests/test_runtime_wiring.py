"""Regression guards for wiring mistakes that unit-testing helpers in
isolation cannot catch.

The GTK layouts/widgets cannot be imported in the dependency-light CI job,
so these checks read the source as AST. They verify that names called at
runtime are actually bound at module scope — several accessibility edits
previously shipped with missing imports while all isolated tests stayed
green and the app raised NameError on the first card bind.
"""

import ast
import os
import sys
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))


def module_level_names(path: Path) -> set[str]:
    """Return names bound at module scope by imports/defs/assignments."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


class RuntimeWiringTests(unittest.TestCase):
    def test_skewed_card_binds_accessible_name_helper(self):
        names = module_level_names(SRC / "widgets" / "skewed_card.py")
        self.assertIn("wallpaper_accessible_name", names)

    def test_parallax_gallery_binds_os_for_focus_labels(self):
        names = module_level_names(SRC / "layouts" / "parallax_gallery.py")
        self.assertIn("os", names)

    def test_stacked_deck_binds_accessible_name_helper(self):
        names = module_level_names(SRC / "layouts" / "stacked_deck.py")
        self.assertIn("wallpaper_accessible_name", names)

    def test_custom_layout_focus_rings_are_gated_on_real_focus(self):
        for name in ("stacked_deck", "radial_fan", "cylindrical_ring"):
            source = (SRC / "layouts" / f"{name}.py").read_text(encoding="utf-8")
            self.assertIn("widget_has_keyboard_focus", source, name)
        gsk = (SRC / "widgets" / "gsk_utils.py").read_text(encoding="utf-8")
        self.assertIn("def widget_has_keyboard_focus", gsk)

    def test_layout_css_uses_display_wide_dedup(self):
        for name in ("wallpaper_carousel", "masonry_grid", "glassmorphism",
                     "parallax_gallery"):
            path = (
                SRC / "widgets" / f"{name}.py" if name == "wallpaper_carousel"
                else SRC / "layouts" / f"{name}.py"
            )
            source = path.read_text(encoding="utf-8")
            self.assertIn("register_css_once", source, name)
            self.assertNotIn("Gtk.StyleContext.add_provider_for_display", source, name)

    def test_horizontal_layouts_can_scroll_with_a_mouse_wheel(self):
        for name in ("wallpaper_carousel", "glassmorphism", "parallax_gallery"):
            path = (
                SRC / "widgets" / f"{name}.py" if name == "wallpaper_carousel"
                else SRC / "layouts" / f"{name}.py"
            )
            source = path.read_text(encoding="utf-8")
            self.assertIn("enable_vertical_wheel_scroll", source, name)
        gsk = (SRC / "widgets" / "gsk_utils.py").read_text(encoding="utf-8")
        self.assertIn("def enable_vertical_wheel_scroll", gsk)

    def test_thumbnail_queue_handles_a_large_visible_page(self):
        source = (SRC / "widgets" / "thumbnail_loader.py").read_text(encoding="utf-8")
        self.assertIn("MAX_QUEUED_JOBS = 512", source)
        self.assertIn("POOL_SIZE = 6", source)

    def test_split_preview_follows_focus(self):
        source = (SRC / "layouts" / "split_screen.py").read_text(encoding="utf-8")
        self.assertIn("self.preview.set_wallpaper_path(item.path)", source)
        self.assertIn('"value-changed", self._on_scroll', source)
        self.assertIn("def _on_scroll", source)

    def test_seamless_mode_wiring(self):
        schema = (Path(__file__).resolve().parents[1] / "data"
                  / "dev.sakib.Wallmat.gschema.xml").read_text(encoding="utf-8")
        self.assertIn('name="seamless-mode"', schema)
        self.assertIn('name="seamless-backdrop"', schema)
        source = (SRC / "window.py").read_text(encoding="utf-8")
        self.assertIn("def _apply_seamless", source)
        self.assertIn("Gdk.KEY_s, Gdk.KEY_S", source)
        self.assertIn("_SEAMLESS_CSS", source)
        self.assertIn("self.add_css_class(f\"wallmat-backdrop-{backdrop}\")", source)
        self.assertIn("surface.set_opaque_region(None)", source)
        settings_src = (SRC / "settings.py").read_text(encoding="utf-8")
        self.assertIn("seamless-mode", settings_src)
        self.assertIn("seamless-backdrop", settings_src)

    def test_layout_selector_removed_with_keyboard_shortcuts(self):
        source = (SRC / "window.py").read_text(encoding="utf-8")
        self.assertNotIn("layout_selector", source)
        self.assertIn("Gdk.KEY_1, Gdk.KEY_2, Gdk.KEY_3, Gdk.KEY_4,", source)
        self.assertIn("Adw.ShortcutsDialog.new()", source)
        self.assertIn("Adw.ShortcutsSection.new", source)
        self.assertIn("Adw.ShortcutsItem.new", source)
        self.assertNotIn("shortcuts_button", source)

    def test_placement_wiring(self):
        schema = (Path(__file__).resolve().parents[1] / "data"
                  / "dev.sakib.Wallmat.gschema.xml").read_text(encoding="utf-8")
        self.assertIn('name="wallpaper-placement"', schema)
        self.assertIn('name="placement-background"', schema)
        window_src = (SRC / "window.py").read_text(encoding="utf-8")
        self.assertIn("apply_gnome_placement", window_src)
        settings_src = (SRC / "settings.py").read_text(encoding="utf-8")
        self.assertIn("def _on_placement", settings_src)
        self.assertTrue((SRC / "placement.py").exists())

    def test_layout_position_restore_wiring(self):
        schema = (Path(__file__).resolve().parents[1] / "data"
                  / "dev.sakib.Wallmat.gschema.xml").read_text(encoding="utf-8")
        self.assertIn('name="layout-positions"', schema)
        source = (SRC / "window.py").read_text(encoding="utf-8")
        self.assertIn("def _save_layout_position", source)
        self.assertIn("def _restore_layout_position", source)
        base = (SRC / "layouts" / "base.py").read_text(encoding="utf-8")
        self.assertIn("def get_position", base)
        self.assertIn("def restore_position", base)
        for name in ("split_screen", "infinite_ribbon", "glassmorphism",
                     "parallax_gallery", "masonry_grid", "radial_fan",
                     "cylindrical_ring", "stacked_deck"):
            layout = (SRC / "layouts" / f"{name}.py").read_text(encoding="utf-8")
            self.assertIn("def get_position", layout, name)
            self.assertIn("def restore_position", layout, name)

    def test_file_details_are_opt_in(self):
        source = (SRC / "window.py").read_text(encoding="utf-8")
        self.assertIn('Gtk.CheckButton(label="Show file details")', source)
        self.assertIn("def _on_details_toggled", source)
        self.assertIn("self._metadata_row.set_visible(False)", source)
        # Selection no longer forces the row visible.
        load_fn = source.split("def _load_selected_metadata")[1].split("def _on_copy_metadata")[0]
        self.assertNotIn("self._metadata_row.set_visible(True)", load_fn)

    def test_no_argument_launch_resolves_folder(self):
        source = (SRC / "window.py").read_text(encoding="utf-8")
        self.assertEqual(source.count("os.path.abspath(wallpaper_dir)"), 0)
        self.assertIn("self._wallpaper_dir = os.path.abspath(initial_directory)", source)
        self.assertIn("self._scan_and_load(self._wallpaper_dir)", source)

    def test_windowless_instance_guard(self):
        source = (SRC / "main.py").read_text(encoding="utf-8")
        self.assertIn("def ensure_window", source)
        self.assertIn("if not app.get_windows()", source)
        self.assertIn("GLib.timeout_add_seconds(5, ensure_window)", source)

    def test_hig_iconography_and_header_subtitle_wiring(self):
        source = (SRC / "window.py").read_text(encoding="utf-8")
        self.assertIn("def _icon_button", source)
        for icon in ("preferences-desktop-wallpaper-symbolic", "view-reveal-symbolic",
                     "color-select-symbolic", "starred-symbolic",
                     "media-playlist-shuffle-symbolic", "edit-copy-symbolic"):
            self.assertIn(icon, source)
        self.assertIn("def _set_window_title(self, title: str, subtitle: str = \"\")", source)
        self.assertIn("self._favorite_button_icon.set_from_icon_name(icon)", source)
        self.assertIn("self._favorites_chip_icon.set_from_icon_name(icon)", source)

    def test_polished_action_layout_wiring(self):
        source = (SRC / "window.py").read_text(encoding="utf-8")
        self.assertIn("Gtk.ToggleButton(icon_name=\"system-search-symbolic\")", source)
        self.assertIn("def _set_search_visible", source)
        self.assertIn("self._set_search_visible(True)", source)
        self.assertIn("self._set_search_visible(False)", source)
        self.assertIn('Gtk.Button(label="Choose wallpaper folder…")', source)
        self.assertIn("self.set_wallpaper_button.add_css_class(\"suggested-action\")", source)
        self.assertNotIn("self.apply_matugen_button.add_css_class", source)
        self.assertNotIn("layout_row.append(self.folder_menu_button)", source)

    def test_filters_popover_wiring(self):
        source = (SRC / "window.py").read_text(encoding="utf-8")
        self.assertIn("filters_popover = Gtk.Popover()", source)
        self.assertIn("self.filters_button = Gtk.MenuButton()", source)
        self.assertIn("def _update_filters_badge", source)
        self.assertIn('self._filters_label.set_label(f"{count}" if count', source)
        self.assertIn("self._header_bar.pack_start(self.filters_button)", source)
        self.assertIn('self.filters_button.add_css_class("flat")', source)
        self.assertIn('widget.add_css_class("flat")', source)
        self.assertIn('self.favorites_filter.add_css_class("flat")', source)
        self.assertIn('filters_popover.add_css_class("wallmat-filter-popover")', source)
        self.assertIn('register_css_once("wallmat-filter-style", display, _FILTER_CSS,\n                          Gtk.STYLE_PROVIDER_PRIORITY_USER)', source)
        css = (SRC / "window.py").read_text(encoding="utf-8")
        self.assertIn("background-color: var(--primary);\n    color: var(--on_primary);", css)
        self.assertIn("dropdown button.toggle:hover label", css)
        self.assertIn("for action_button in (self.preview_button, self.set_wallpaper_button):", source)
        self.assertNotIn("self.filters_button.set_halign(Gtk.Align.CENTER)", source)
        for key in ("Sort", "Tag", "Color", "Collection", "Recent"):
            self.assertIn(f'filters_box.append(filter_chip("{key}"', source)
        self.assertIn('Gtk.Image.new_from_icon_name("non-starred-symbolic")', source)
        self.assertNotIn("content.append(self.filters_button)", source)

    def test_adwaita_chrome_with_transparent_backdrop(self):
        source = (SRC / "window.py").read_text(encoding="utf-8")
        for name in ("Adw.WindowTitle", "Adw.HeaderBar", "Adw.ToolbarView",
                     "_set_window_title", "set_show_end_title_buttons"):
            self.assertIn(name, source)
        self.assertIn("self._toolbar_view.set_content(content)", source)
        self.assertIn("self.set_content(self._toolbar_view)", source)
        self.assertIn('self._header_bar.set_visible(not self._plain and not enabled)', source)
        self.assertIn("headerbar.background", source)
        self.assertIn("Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION", source)
        self.assertIn("border-radius: 12px", source)

    def test_optional_catalog_wiring(self):
        window_src = (SRC / "window.py").read_text(encoding="utf-8")
        self.assertIn("def _on_browse_catalog", window_src)
        self.assertIn("catalog_search(text, on_results)", window_src)
        self.assertIn("catalog_download(item, target_dir, on_downloaded)", window_src)
        self.assertIn("Browse online catalog", window_src)
        self.assertIn("attribution_text(item)", window_src)
        self.assertIn('selection.connect("notify::selected", on_selected_changed)', window_src)
        client_src = (SRC / "catalog_client.py").read_text(encoding="utf-8")
        self.assertIn("MIN_REQUEST_INTERVAL", client_src)
        self.assertIn("os.replace(temporary, final)", client_src)
        self.assertIn("_decode_image(temporary)", client_src)
        self.assertIn("validate_download_url(response.geturl())", client_src)

    def test_target_routing_wiring(self):
        window_src = (SRC / "window.py").read_text(encoding="utf-8")
        self.assertIn("def _detect_targets", window_src)
        self.assertIn("def _resolve_target", window_src)
        self.assertIn("set_on=portal_set_on(target)", window_src)
        self.assertIn("def _apply_wallpaper_gsettings(self, path, target=", window_src)
        portal_src = (SRC / "portal_wallpaper.py").read_text(encoding="utf-8")
        self.assertIn("def request_wallpaper(path, callback, set_on=", portal_src)
        self.assertIn('GLib.Variant("s", set_on)', portal_src)
        settings_src = (SRC / "settings.py").read_text(encoding="utf-8")
        self.assertIn("supported_targets(*self._target_capabilities())", settings_src)
        daemon_src = (SRC / "schedule_daemon.py").read_text(encoding="utf-8")
        self.assertIn("apply_wallpaper(chosen, resolve_target(preference))", daemon_src)

    def test_backup_export_section_picker_wiring(self):
        source = (SRC / "window.py").read_text(encoding="utf-8")
        self.assertIn("Export backup sections", source)
        self.assertIn("sections=selected", source)
        self.assertIn("Select at least one section to export.", source)
        self.assertIn("if imported[\"favorites\"] is not None", source)
        self.assertIn("if imported[\"preferences\"] is not None", source)
        storage = (SRC / "backup_storage.py").read_text(encoding="utf-8")
        self.assertIn("BACKUP_SECTIONS", storage)

    def test_close_saves_current_layout_position(self):
        source = (SRC / "window.py").read_text(encoding="utf-8")
        tree = ast.parse(source, filename="window.py")
        close_fn = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
            and node.name == "_on_window_close_request"
        )
        calls = {
            getattr(node.func, "attr", None)
            for node in ast.walk(close_fn)
            if isinstance(node, ast.Call)
        }
        self.assertIn("_save_layout_position", calls)

    def test_daemon_scans_library_for_period_candidates(self):
        source = (SRC / "schedule_daemon.py").read_text(encoding="utf-8")
        tree = ast.parse(source, filename="schedule_daemon.py")
        calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and getattr(node.func, "id", None) == "period_candidates"
        ]
        self.assertEqual(len(calls), 1)
        # The folder-path argument must come from a real scan; an empty list
        # means every library-source schedule is silently skipped by the
        # background service while the app is closed.
        self.assertGreaterEqual(len(calls[0].args), 3)
        self.assertNotIsInstance(calls[0].args[2], ast.List)
        self.assertIn("folder_paths = scan_wallpapers", source)

    def test_placement_applies_on_portal_path(self):
        source = (SRC / "window.py").read_text(encoding="utf-8")
        self.assertIn("def _apply_placement_mode", source)
        # Both the GSettings fallback and the Wayland portal success path must
        # apply the chosen placement mode; previously only the fallback did.
        self.assertEqual(source.count("self._apply_placement_mode()"), 2)

    def test_base_select_path_restores_saved_focus(self):
        base = (SRC / "layouts" / "base.py").read_text(encoding="utf-8")
        self.assertIn("self._paths.index(path)", base)
        self.assertIn("self.restore_position(index)", base)

    def test_schedule_dialog_describes_independent_timers(self):
        source = (SRC / "window.py").read_text(encoding="utf-8")
        self.assertIn("independently of auto-rotation", source)
        self.assertNotIn("apply only while auto-rotation", source)

    def test_schedule_wiring(self):
        schema = (Path(__file__).resolve().parents[1] / "data"
                  / "dev.sakib.Wallmat.gschema.xml").read_text(encoding="utf-8")
        self.assertIn('name="rotation-schedule"', schema)
        source = (SRC / "window.py").read_text(encoding="utf-8")
        self.assertIn("def _on_manage_schedule", source)
        self.assertIn("def _schedule_candidates", source)
        self.assertIn("active_period(periods, now.hour", source)
        self.assertIn("self.manage_schedule_button", source)
        self.assertIn("def _on_schedule_tick", source)
        self.assertTrue((SRC / "schedule.py").exists())
        self.assertTrue((SRC / "schedule_daemon.py").exists())
        installer = (Path(__file__).resolve().parents[1] / "install.sh").read_text()
        self.assertIn("dev.sakib.Wallmat.Schedule.desktop", installer)

    def test_preview_uses_cached_thumbnail(self):
        source = (SRC / "widgets" / "desktop_preview.py").read_text(encoding="utf-8")
        self.assertIn("cache/wallpaper-chooser/thumbs", source)
        self.assertIn(".webp", source)
        self.assertIn("os.path.isfile(thumb)", source)
        self.assertIn("source = thumb", source)

    def test_palettes_precomputed_at_scan(self):
        source = (SRC / "window.py").read_text(encoding="utf-8")
        self.assertIn("self._start_palette_scan(silent=True)", source)
        self.assertIn("def _start_palette_scan(self, silent=False)", source)
        self.assertIn("self._palette_scan_silent = silent", source)
        self.assertIn("if not self._palette_scan_silent:", source)

    def test_color_filter_stable_loading(self):
        source = (SRC / "window.py").read_text(encoding="utf-8")
        self.assertIn("self._palette_scanning = True", source)
        self.assertIn("def _palette_scan_done", source)
        self.assertIn("GLib.idle_add(self._palette_scan_done, generation)", source)
        self.assertIn(
            "self._color_filter\n                if not getattr(self, \"_palette_scanning\", False) else None",
            source,
        )
        self.assertIn("cache_path=cache_path", source)
        palette = (SRC / "color_palette.py").read_text(encoding="utf-8")
        self.assertIn("def extract_families(path: str, size: int = 32, cache_path", palette)

    def test_color_filter_wiring(self):
        source = (SRC / "window.py").read_text(encoding="utf-8")
        self.assertIn("ensure_pixbuf_loaded()", source)
        self.assertIn("self.color_filter = Gtk.DropDown.new_from_strings", source)
        self.assertIn("def _start_palette_scan", source)
        self.assertIn("def _palettes_ready", source)
        self.assertTrue((SRC / "color_palette.py").exists())

    def test_desktop_launcher_templates_and_installer(self):
        root = Path(__file__).resolve().parents[1]
        desktop = (root / "data" / "dev.sakib.Wallmat.desktop").read_text(encoding="utf-8")
        self.assertIn("[Desktop Entry]", desktop)
        self.assertIn("Exec=@WALLMAT_EXEC@", desktop)
        # TryExec must be a bare executable; a full command with arguments
        # makes GDesktopAppInfo reject the entry and hides it from search.
        self.assertIn("TryExec=python3", desktop)
        self.assertNotIn("TryExec=@WALLMAT_EXEC@", desktop)
        self.assertIn("Icon=dev.sakib.Wallmat", desktop)
        self.assertIn("StartupWMClass=wallmat", desktop)
        settings = (root / "data" / "dev.sakib.Wallmat.Settings.desktop").read_text(
            encoding="utf-8"
        )
        self.assertIn("Exec=@SETTINGS_EXEC@", settings)
        self.assertTrue((root / "data" / "dev.sakib.Wallmat.svg").exists())
        installer = (root / "install.sh").read_text(encoding="utf-8")
        self.assertIn("--uninstall", installer)
        self.assertIn("glib-compile-schemas", installer)
        self.assertIn("icons/hicolor/index.theme", installer)
        self.assertIn("gtk-update-icon-cache", installer)

    def test_settings_app_and_shared_preferences(self):
        schema = (Path(__file__).resolve().parents[1] / "data"
                  / "dev.sakib.Wallmat.gschema.xml").read_text(encoding="utf-8")
        for key in ("matugen-args", "wallpaper-target", "thumbnail-cache-limit-mb"):
            self.assertIn(f'name="{key}"', schema)
        settings_src = (SRC / "settings.py").read_text(encoding="utf-8")
        self.assertIn("Adw.PreferencesWindow", settings_src)
        self.assertIn("def _browsing_page", settings_src)
        self.assertIn("def _wallpaper_page", settings_src)
        self.assertIn("def _storage_page", settings_src)
        backup = (SRC / "backup_storage.py").read_text(encoding="utf-8")
        self.assertIn('"wallpaper-target"', backup)
        self.assertIn('"thumbnail-cache-limit-mb": (64, 4096)', backup)
        window_src = (SRC / "window.py").read_text(encoding="utf-8")
        self.assertIn("def connect_changed", window_src)
        self.assertIn("def _connect_setting_changes", window_src)

    def test_parallax_centres_the_focused_card_with_measured_stride(self):
        source = (SRC / "layouts" / "parallax_gallery.py").read_text(encoding="utf-8")
        self.assertIn("def _stride", source)
        self.assertIn("adjustment.get_upper() / n", source)
        self.assertIn("position * stride + stride / 2.0 + 6.0 - viewport_width / 2.0", source)

    def test_parallax_hides_the_tall_row_ring_and_keeps_the_card_ring(self):
        source = (SRC / "layouts" / "parallax_gallery.py").read_text(encoding="utf-8")
        self.assertIn(".wallmat-parallax row:focus", source)
        self.assertIn(".wallmat-parallax listitem:focus", source)
        self.assertIn(".parallax-fg.focused {\n    opacity: 1.0;\n    box-shadow: 0 0 0 3px {ring};", source)

    def test_glassmorphism_focus_ring_is_drawn_on_the_card(self):
        source = (SRC / "layouts" / "glassmorphism.py").read_text(encoding="utf-8")
        self.assertNotIn("_FocusFrame", source)
        self.assertNotIn("_focus_frame", source)
        self.assertIn(".glass-card.focused {\n    filter: none;\n    box-shadow: 0 0 0 3px {ring};", source)
        # The tall GTK row outline stays suppressed so only one ring shows.
        self.assertIn(".wallmat-glass row:focus", source)

    def test_glassmorphism_derives_scroll_stride_from_the_adjustment(self):
        source = (SRC / "layouts" / "glassmorphism.py").read_text(encoding="utf-8")
        self.assertIn("def _stride", source)
        self.assertIn("adjustment.get_upper() / n", source)
        self.assertIn("position * stride + stride / 2.0 + 6.0 - viewport_width / 2.0", source)

    def test_glassmorphism_suppresses_the_tall_listitem_focus_outline(self):
        source = (SRC / "layouts" / "glassmorphism.py").read_text(encoding="utf-8")
        self.assertIn(".wallmat-glass row:focus", source)
        self.assertIn(".wallmat-glass listitem:focus", source)
        self.assertIn(".glass-card.focused", source)

    def test_focused_glass_card_is_not_dimmed(self):
        source = (SRC / "layouts" / "glassmorphism.py").read_text(encoding="utf-8")
        self.assertIn("filter: brightness(0.55);", source)
        self.assertIn(".glass-card.focused {\n    filter: none;", source)
        self.assertNotIn("opacity: 0.5;", source)

    def test_radial_fan_uses_a_bounded_window(self):
        source = (SRC / "layouts" / "radial_fan.py").read_text(encoding="utf-8")
        self.assertIn("FAN_WINDOW =", source)
        self.assertIn("def _fan_rels", source)
        self.assertIn("self._rels = _fan_rels(len(paths))", source)
        self.assertIn("rels = self._rels", source)
        self.assertIn("MAX_TEXTURES =", source)
        self.assertNotIn("sorted(range(-(n // 2)", source)

    def test_ring_cards_scale_with_cosine_to_avoid_overlap(self):
        source = (SRC / "layouts" / "cylindrical_ring.py").read_text(encoding="utf-8")
        self.assertIn("def _card_scale", source)
        self.assertIn("return max(0.35, math.cos(theta))", source)
        self.assertIn("snapshot.scale(scale, scale)", source)
        self.assertNotIn(".perspective(CAMERA_DEPTH)", source)

    def test_carousel_prominence_uses_viewport_coordinates(self):
        source = (SRC / "widgets" / "wallpaper_carousel.py").read_text(encoding="utf-8")
        self.assertIn("viewport_center = viewport_width / 2.0", source)
        self.assertNotIn("scroll_x = self._hadjustment.get_value()", source)

    def test_carousel_reuses_items_across_rebuilds(self):
        source = (SRC / "widgets" / "wallpaper_carousel.py").read_text(encoding="utf-8")
        self.assertIn("self._item_cache", source)

    def test_parallax_tracks_background_widgets_separately(self):
        path = SRC / "layouts" / "parallax_gallery.py"
        source = path.read_text(encoding="utf-8")
        self.assertIn("_live_bg", source)
        self.assertIn('bg_factory.connect("unbind", self._on_bg_unbind)', source)

        tree = ast.parse(source, filename=str(path))
        functions = {
            node.name: node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        bg_bind = ast.get_source_segment(source, functions["_on_bg_bind"])
        fg_bind = ast.get_source_segment(source, functions["_on_fg_bind"])
        # Both layers register in their own map and use one shared decode
        # path; the old per-layer map mix-up must not come back.
        self.assertIn("self._live_bg[item.path] = picture", bg_bind)
        self.assertIn("self._live_fg[item.path] = picture", fg_bind)
        self.assertIn("self._ensure_thumbnail(item.path)", bg_bind)
        self.assertIn("self._ensure_thumbnail(item.path)", fg_bind)
        self.assertNotIn("bg_loader", source)
        self.assertNotIn("fg_loader", source)


if __name__ == "__main__":
    unittest.main()
