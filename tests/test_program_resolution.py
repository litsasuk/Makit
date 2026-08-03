from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from execution.programs import ProgramResolver, ToolUnavailable


class ProgramResolutionTests(unittest.TestCase):
    def test_missing_script_is_reported_without_required_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            resolver = ProgramResolver(Path(temporary_directory))

            with self.assertRaisesRegex(ToolUnavailable, "Python 脚本不存在"):
                resolver.resolve_required(
                    "demo", {"script": "tools\\demo\\missing.py"}
                )


if __name__ == "__main__":
    unittest.main()
