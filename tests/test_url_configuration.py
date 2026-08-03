from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from tooling.arguments import build_arguments
from tooling.models import TargetInput
from tooling.registry import load_tools


PROJECT_DIR = Path(__file__).resolve().parents[1]


class UrlConfigurationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = json.loads(
            (PROJECT_DIR / "config.demo.json").read_text(encoding="utf-8")
        )
        cls.tools = load_tools(cls.config)

    def test_every_mode_explicitly_configures_url_behavior(self) -> None:
        for tool_id, raw_tool in self.config["tools"].items():
            for mode_id, raw_mode in raw_tool["modes"].items():
                with self.subTest(tool=tool_id, mode=mode_id):
                    self.assertIsInstance(raw_mode.get("requires_url"), bool)
                    if raw_mode["requires_url"]:
                        self.assertIn("url_args", raw_mode)
                        self.assertNotIn("args", raw_mode)
                    else:
                        self.assertIn("args", raw_mode)
                        self.assertNotIn("url_args", raw_mode)

    def test_single_url_and_url_file_arguments_are_rendered(self) -> None:
        tool = self.tools["exe_cli_demo"]
        single = TargetInput(
            kind="url",
            display_value="https://example.test",
            urls=("https://example.test",),
        )
        listed = TargetInput(
            kind="file",
            display_value="targets.txt",
            urls=("https://one.test", "https://two.test:8443/path"),
            source_file=Path("targets.txt"),
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            output_dir = Path(temporary_directory)
            single_arguments = build_arguments(
                tool, "check", single, output_dir
            )
            list_arguments = build_arguments(tool, "check", listed, output_dir)

            self.assertEqual(single_arguments[:2], ["--url", single.urls[0]])
            self.assertEqual(list_arguments[0], "--url-file")
            self.assertEqual(Path(list_arguments[1]), output_dir / "targets.txt")
            self.assertEqual(
                (output_dir / "targets.txt").read_text(encoding="utf-8"),
                "https://one.test\nhttps://two.test:8443/path\n",
            )

    def test_legacy_mode_schema_is_rejected(self) -> None:
        config = copy.deepcopy(self.config)
        mode = config["tools"]["exe_cli_demo"]["modes"]["check"]
        mode.pop("requires_url")
        mode["args"] = mode.pop("url_args")

        with self.assertRaisesRegex(ValueError, "requires_url"):
            load_tools(config)


if __name__ == "__main__":
    unittest.main()
