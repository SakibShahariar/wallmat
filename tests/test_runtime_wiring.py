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
        # The background completion guard must consult the background map;
        # the foreground one must consult the foreground map.
        self.assertIn("if self._live_bg.get(item_id) is picture", bg_bind)
        self.assertNotIn("if self._live_fg.get(item_id) is picture", bg_bind)
        self.assertIn("if self._live_fg.get(item_id) is picture", fg_bind)


if __name__ == "__main__":
    unittest.main()
