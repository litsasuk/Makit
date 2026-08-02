"""运行会话目录与结果模型。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class RunSession:
    directory: Path
    commands_file: Path


@dataclass(frozen=True)
class RunResult:
    tool_id: str
    return_code: int
    output_file: Path

    @property
    def success(self) -> bool:
        return self.return_code == 0


def create_session(output_root: Path, target: str) -> RunSession:
    safe_target = re.sub(r"[^0-9A-Za-z._-]+", "_", target).strip("._")
    safe_target = (safe_target or "target")[:80]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    directory = output_root / f"{timestamp}_{safe_target}"
    directory.mkdir(parents=True, exist_ok=False)
    return RunSession(directory=directory, commands_file=directory / "commands.txt")
