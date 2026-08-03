from __future__ import annotations

from io import StringIO
import unittest
from unittest.mock import patch

from console.app import edit_tool_command
from console.ui import _move_vertical_cursor
from execution.runner import format_command, parse_command


class CommandEditingTests(unittest.TestCase):
    def test_format_and_parse_round_trip(self) -> None:
        command = [
            r"C:\Program Files\Tool\tool.exe",
            "--url",
            "https://example.test/a b",
            "--name",
            'a "quoted" value',
        ]

        self.assertEqual(parse_command(format_command(command)), command)

    def test_edit_can_append_arguments_and_restore_secret(self) -> None:
        command = [
            r"C:\Tools\tool.exe",
            "--header",
            "Authorization: secret-token",
        ]

        def append_argument(prompt: object, initial_value: str | None = None) -> str:
            self.assertEqual(prompt, "command > ")
            self.assertIsNotNone(initial_value)
            assert initial_value is not None
            self.assertNotIn("secret-token", initial_value)
            return initial_value + " --threads 8"

        with (
            patch("console.app.read_console_input", side_effect=append_argument),
            patch("sys.stdout", new=StringIO()),
        ):
            edited, sensitive_values = edit_tool_command(
                command, ("Authorization: secret-token",)
            )

        self.assertEqual(edited[-2:], ["--threads", "8"])
        self.assertEqual(edited[2], "Authorization: secret-token")
        self.assertEqual(sensitive_values, ("Authorization: secret-token",))

    def test_empty_command_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "不能为空"):
            parse_command("   ")

    def test_up_and_down_move_inside_wrapped_command(self) -> None:
        command = "x" * 200

        moved_up = _move_vertical_cursor(command, 150, 10, 80, -1)
        moved_down = _move_vertical_cursor(command, moved_up, 10, 80, 1)

        self.assertEqual(moved_up, 70)
        self.assertEqual(moved_down, 150)
        self.assertEqual(_move_vertical_cursor(command, 20, 10, 80, -1), 0)
        self.assertEqual(_move_vertical_cursor(command, 190, 10, 80, 1), 200)


if __name__ == "__main__":
    unittest.main()
