from __future__ import annotations

from io import BytesIO, StringIO, TextIOWrapper
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from execution.runner import Runner, create_session


class _ProgressStream(StringIO):
    def __init__(self, value: str) -> None:
        super().__init__(value)
        self.configured_newline: str | None = None

    def reconfigure(self, *, newline: str | None = None, **kwargs: object) -> None:
        self.configured_newline = newline


class _FakeProcess:
    def __init__(self, stdout: StringIO | TextIOWrapper) -> None:
        self.stdout = stdout
        self.pid = 12345

    def wait(self, timeout: float | None = None) -> int:
        return 0


class RunnerProgressTests(unittest.TestCase):
    def test_interactive_pipe_preserves_carriage_returns(self) -> None:
        config = {
            "output_dir": "output",
            "tools": {
                "demo": {
                    "executable": sys.executable,
                    "encoding": "utf-8",
                    "interactive": True,
                }
            },
        }
        progress_stream = _ProgressStream("first\rsecond\r")
        fake_process = _FakeProcess(progress_stream)

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            runner = Runner(root, config)
            session = create_session(root / "output", "progress")
            terminal_output = StringIO()
            with (
                patch(
                    "execution.runner.subprocess.Popen", return_value=fake_process
                ) as popen,
                patch("sys.stdout", new=terminal_output),
            ):
                result = runner.run("demo", [], session)

        self.assertEqual(result.return_code, 0)
        self.assertEqual(progress_stream.configured_newline, "")
        self.assertIn("first\rsecond\r", terminal_output.getvalue())
        environment = popen.call_args.kwargs["env"]
        self.assertEqual(environment["MAKIT_FORCE_COLOR"], "1")
        self.assertEqual(environment["FORCE_COLOR"], "1")
        self.assertEqual(environment["CLICOLOR_FORCE"], "1")

    def test_noninteractive_progress_redraws_and_logs_only_final_state(self) -> None:
        config = {
            "output_dir": "output",
            "tools": {
                "demo": {
                    "executable": sys.executable,
                    "encoding": "utf-8",
                    "interactive": False,
                }
            },
        }
        progress_stream = TextIOWrapper(
            BytesIO(b"first\rsecond\r"), encoding="utf-8"
        )
        fake_process = _FakeProcess(progress_stream)

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            runner = Runner(root, config)
            session = create_session(root / "output", "progress")
            terminal_output = StringIO()
            with (
                patch("execution.runner.subprocess.Popen", return_value=fake_process),
                patch("sys.stdout", new=terminal_output),
            ):
                result = runner.run("demo", [], session)
            log_output = result.output_file.read_text(encoding="utf-8")

        self.assertIn("\rfirst\rsecond\n", terminal_output.getvalue())
        self.assertEqual(log_output, "second\n")


if __name__ == "__main__":
    unittest.main()
