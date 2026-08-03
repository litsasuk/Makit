from __future__ import annotations

from io import StringIO
import unittest
from unittest.mock import patch

from console.rendering import show_table


class TableRenderingTests(unittest.TestCase):
    def _render(self, title: str) -> list[str]:
        output = StringIO()
        with patch("sys.stdout", new=output):
            show_table(title, ("#", "Name"), [(1, "demo")])
        return output.getvalue().splitlines()

    def test_navigation_tables_have_no_title_rule(self) -> None:
        for title in ("Operation Modes", "Reverse Modules", "Modes (wxapkg)"):
            with self.subTest(title=title):
                lines = self._render(title)
                self.assertEqual(lines[0], title)
                self.assertTrue(lines[1].lstrip().startswith("#"))

    def test_other_tables_keep_title_rule(self) -> None:
        lines = self._render("Core Commands")
        self.assertEqual(lines[1], "=" * len("Core Commands"))


if __name__ == "__main__":
    unittest.main()
