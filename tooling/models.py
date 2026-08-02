"""工具、模式和目标输入的数据模型。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TestMode:
    id: str
    name: str
    description: str
    arguments: tuple[str, ...]
    list_arguments: tuple[str, ...] | None
    requires_target: bool = True


@dataclass(frozen=True)
class Tool:
    id: str
    module: str
    console_mode: str
    description: str
    header_arguments: tuple[str, ...] | None
    cookie_arguments: tuple[str, ...] | None
    launch_only: bool
    run_as_admin: bool
    default_mode: str
    modes: tuple[TestMode, ...]

    def supports_header(self, name: str) -> bool:
        return self.header_arguments is not None or (
            name.lower() == "cookie" and self.cookie_arguments is not None
        )

    def sensitive_header_values(self, headers: tuple[str, ...]) -> tuple[str, ...]:
        values = list(headers)
        if self.header_arguments is None and self.cookie_arguments is not None:
            values.extend(
                value.strip()
                for name, value in (header.split(":", 1) for header in headers)
                if name.strip().lower() == "cookie"
            )
        return tuple(values)


@dataclass(frozen=True)
class TargetInput:
    kind: str
    display_value: str
    urls: tuple[str, ...]
    source_file: Path | None = None

    @property
    def is_list(self) -> bool:
        return self.kind == "file"

    @property
    def session_label(self) -> str:
        if self.source_file is None:
            return self.urls[0]
        return f"{self.source_file.stem}_{len(self.urls)}_targets"
