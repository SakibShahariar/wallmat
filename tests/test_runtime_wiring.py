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

    def test_focused_glass_card_is_not_dimmed(self):
        source = (SRC / "layouts" / "glassmorphism.py").read_text(encoding="utf-8")
        self.assertIn(".glass-card.focused {\n    opacity: 1.0;", source)

    def test_radial_fan_centers_its_fan_vertically(self):
        source = (SRC / "layouts" / "radial_fan.py").read_text(encoding="utf-8")
        self.assertIn("radius_by_height", source)
        self.assertNotIn("radius = min(width * 0.55, available_radius)", source)

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
