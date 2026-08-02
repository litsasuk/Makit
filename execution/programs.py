"""统一描述并解析 EXE、Python 脚本和 Java JAR。"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping


class ToolUnavailable(RuntimeError):
    """配置的外部工具不可用。"""


class ProgramKind(str, Enum):
    EXECUTABLE = "executable"
    PYTHON = "python"
    JAVA = "java"


@dataclass(frozen=True)
class ProgramSpec:
    """与 CLI/GUI 无关的程序启动描述。"""

    kind: ProgramKind
    source: str
    interpreter: str | None = None


@dataclass(frozen=True)
class ResolvedProgram:
    """已解析为绝对路径的安全参数数组。"""

    spec: ProgramSpec
    source: Path
    command: tuple[str, ...]

    @property
    def executable(self) -> Path:
        return Path(self.command[0])


def _required_text(value: object, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{location} 必须是非空字符串")
    return value.strip()


def program_spec_from_config(
    tool_config: Mapping[str, Any], location: str = "tool"
) -> ProgramSpec:
    """校验并返回唯一的程序类型配置。"""
    configured_sources = [
        name
        for name in ("executable", "script", "jar")
        if tool_config.get(name) is not None
    ]
    if len(configured_sources) != 1:
        raise ValueError(
            f"{location} 必须且只能配置 executable、script、jar 中的一项"
        )

    source_field = configured_sources[0]
    source = _required_text(tool_config.get(source_field), f"{location}.{source_field}")
    python_executable = tool_config.get("python_executable")
    java_executable = tool_config.get("java_executable")

    if source_field == "executable":
        if python_executable is not None:
            raise ValueError(
                f"{location}.python_executable 仅能与 script 一起配置"
            )
        if java_executable is not None:
            raise ValueError(f"{location}.java_executable 仅能与 jar 一起配置")
        return ProgramSpec(ProgramKind.EXECUTABLE, source)

    if source_field == "script":
        if Path(source).suffix.lower() != ".py":
            raise ValueError(f"{location}.script 必须指向 .py 文件")
        if java_executable is not None:
            raise ValueError(f"{location}.java_executable 仅能与 jar 一起配置")
        interpreter = (
            _required_text(python_executable, f"{location}.python_executable")
            if python_executable is not None
            else None
        )
        return ProgramSpec(ProgramKind.PYTHON, source, interpreter)

    if Path(source).suffix.lower() != ".jar":
        raise ValueError(f"{location}.jar 必须指向 .jar 文件")
    if python_executable is not None:
        raise ValueError(f"{location}.python_executable 仅能与 script 一起配置")
    interpreter = (
        _required_text(java_executable, f"{location}.java_executable")
        if java_executable is not None
        else None
    )
    return ProgramSpec(ProgramKind.JAVA, source, interpreter)


def validate_program_config(
    tool_config: Mapping[str, Any], location: str
) -> None:
    program_spec_from_config(tool_config, location)


class ProgramResolver:
    """CLI 与 GUI 共用的程序路径、解释器和工作目录解析器。"""

    def __init__(self, project_dir: Path) -> None:
        self.project_dir = project_dir.resolve()

    def _resolve_program(self, configured: object) -> Path | None:
        # 保留早期配置的兼容入口；新 Python 工具应使用 script。
        if configured == "__python__":
            return Path(sys.executable).resolve()
        if not isinstance(configured, str) or not configured.strip():
            return None
        configured = configured.strip()
        candidate = Path(os.path.expandvars(configured))
        if candidate.is_absolute():
            return candidate.resolve() if candidate.is_file() else None

        project_candidate = (self.project_dir / candidate).resolve()
        if project_candidate.is_file():
            return project_candidate
        resolved = shutil.which(configured)
        return Path(resolved).resolve() if resolved else None

    def _resolve_file(self, configured: str) -> Path | None:
        candidate = Path(os.path.expandvars(configured))
        if not candidate.is_absolute():
            candidate = self.project_dir / candidate
        return candidate.resolve() if candidate.is_file() else None

    def _resolve_python(self, configured: str | None) -> Path | None:
        if configured is not None:
            return self._resolve_program(configured)
        path_python = self._resolve_program("python")
        if path_python is not None:
            return path_python
        current = Path(sys.executable)
        return current.resolve() if current.is_file() else None

    def _resolve_java(self, configured: str | None) -> Path | None:
        if configured is not None:
            return self._resolve_program(configured)
        path_java = self._resolve_program("java")
        if path_java is not None:
            return path_java
        java_home = os.environ.get("JAVA_HOME", "").strip()
        if java_home:
            java_name = "java.exe" if os.name == "nt" else "java"
            candidate = Path(os.path.expandvars(java_home)) / "bin" / java_name
            if candidate.is_file():
                return candidate.resolve()
        return None

    def required_files_available(self, tool_config: Mapping[str, Any]) -> bool:
        for configured in tool_config.get("required_files", []):
            if not isinstance(configured, str):
                return False
            if self._resolve_file(configured) is None:
                return False
        return True

    def resolve_required(
        self, tool_id: str, tool_config: Mapping[str, Any]
    ) -> ResolvedProgram:
        if not self.required_files_available(tool_config):
            raise ToolUnavailable(
                f"工具 {tool_id!r} 缺少 required_files 中的文件"
            )

        spec = program_spec_from_config(tool_config, f"tools.{tool_id}")
        if spec.kind is ProgramKind.EXECUTABLE:
            executable = self._resolve_program(spec.source)
            if executable is None:
                raise ToolUnavailable(
                    f"工具 {tool_id!r} 不可用，请修改 config.json 中的路径："
                    f"{spec.source}"
                )
            return ResolvedProgram(spec, executable, (str(executable),))

        source = self._resolve_file(spec.source)
        if source is None:
            label = "Python 脚本" if spec.kind is ProgramKind.PYTHON else "JAR 文件"
            raise ToolUnavailable(
                f"工具 {tool_id!r} 的 {label}不存在：{spec.source}"
            )

        if spec.kind is ProgramKind.PYTHON:
            interpreter = self._resolve_python(spec.interpreter)
            if interpreter is None:
                detail = spec.interpreter or "PATH 中的 python 或 Makit 当前 Python"
                raise ToolUnavailable(
                    f"工具 {tool_id!r} 找不到 Python：{detail}；"
                    "请配置 python_executable"
                )
            command = (str(interpreter), "-u", str(source))
        else:
            interpreter = self._resolve_java(spec.interpreter)
            if interpreter is None:
                detail = spec.interpreter or "PATH 中的 java 或 JAVA_HOME"
                raise ToolUnavailable(
                    f"工具 {tool_id!r} 找不到 Java：{detail}；"
                    "请配置 java_executable"
                )
            command = (str(interpreter), "-jar", str(source))
        return ResolvedProgram(spec, source, command)

    def _configured_working_directory(
        self, tool_config: Mapping[str, Any]
    ) -> Path | None:
        configured = tool_config.get("working_directory")
        if not isinstance(configured, str) or not configured.strip():
            return None
        candidate = Path(os.path.expandvars(configured.strip()))
        if not candidate.is_absolute():
            candidate = self.project_dir / candidate
        return candidate.resolve() if candidate.is_dir() else None

    def working_directory(
        self,
        tool_id: str,
        tool_config: Mapping[str, Any],
        resolved: ResolvedProgram,
        *,
        launch: bool,
    ) -> Path:
        if tool_config.get("working_directory") is not None:
            configured = self._configured_working_directory(tool_config)
            if configured is None:
                raise ToolUnavailable(
                    f"工具 {tool_id!r} 的工作目录不存在："
                    f"{tool_config.get('working_directory')}"
                )
            return configured
        return resolved.source.parent if launch else self.project_dir

    def resolve_optional(
        self, tool_id: str, tool_config: Mapping[str, Any]
    ) -> ResolvedProgram | None:
        try:
            resolved = self.resolve_required(tool_id, tool_config)
            self.working_directory(
                tool_id, tool_config, resolved, launch=False
            )
            return resolved
        except (ToolUnavailable, ValueError):
            return None
