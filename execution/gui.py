"""隔离 GUI 标准流，检测启动期退出并返回结构化结果。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


MAX_ERROR_OUTPUT_BYTES = 8192


def _captured_output(output: Any, encoding: str) -> str:
    output.flush()
    output.seek(0)
    raw_output = output.read()
    if len(raw_output) > MAX_ERROR_OUTPUT_BYTES:
        raw_output = raw_output[-MAX_ERROR_OUTPUT_BYTES:]
    try:
        return raw_output.decode(encoding, errors="replace").strip()
    except LookupError:
        return raw_output.decode("utf-8", errors="replace").strip()


def launch_gui(
    command: list[str],
    working_directory: Path,
    encoding: str = "utf-8",
    startup_timeout: float = 2.0,
) -> dict[str, object]:
    """独立启动 GUI；进程在观察期内退出时返回其输出和退出码。"""
    if not command:
        return {"ok": False, "error": "GUI 启动命令为空"}
    executable = Path(os.path.expandvars(command[0])).resolve()
    if not executable.is_file():
        return {"ok": False, "error": f"启动程序不存在：{executable}"}
    if not working_directory.is_dir():
        return {"ok": False, "error": f"工作目录不存在：{working_directory}"}
    command = [str(executable), *command[1:]]

    creation_flags = subprocess.DETACHED_PROCESS if os.name == "nt" else 0
    with tempfile.TemporaryFile(mode="w+b") as captured:
        try:
            process = subprocess.Popen(
                command,
                cwd=working_directory,
                stdin=subprocess.DEVNULL,
                stdout=captured,
                stderr=subprocess.STDOUT,
                shell=False,
                creationflags=creation_flags,
                start_new_session=os.name != "nt",
            )
        except OSError as exc:
            return {"ok": False, "error": str(exc)}

        deadline = time.monotonic() + max(0.0, startup_timeout)
        while True:
            return_code = process.poll()
            if return_code is not None:
                return {
                    "ok": False,
                    "return_code": return_code,
                    "output": _captured_output(captured, encoding),
                }
            if time.monotonic() >= deadline:
                return {"ok": True, "pid": process.pid}
            time.sleep(0.1)


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) < 5:
        return 2

    status_file = Path(arguments[0])
    working_directory = Path(os.path.expandvars(arguments[1])).resolve()
    encoding = arguments[2]
    try:
        startup_timeout = float(arguments[3])
    except ValueError:
        return 3
    result = launch_gui(
        arguments[4:],
        working_directory,
        encoding,
        startup_timeout,
    )
    try:
        status_file.write_text(
            json.dumps(result, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        return 4
    return 0 if result.get("ok") else 5


if __name__ == "__main__":
    raise SystemExit(main())
