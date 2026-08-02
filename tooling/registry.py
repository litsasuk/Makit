"""配置驱动的工具注册、目标校验和命令参数渲染。"""

from __future__ import annotations

import re
from typing import Any

from execution.programs import validate_program_config
from tooling.models import TargetInput, TestMode, Tool
from tooling.targets import (
    host_from_target,
    load_target_input,
    normalize_target,
    validate_target,
)


TOOL_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
PLACEHOLDER_PATTERN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
ALLOWED_PLACEHOLDERS = frozenset({"target", "host", "output_dir"})
LIST_PLACEHOLDERS = frozenset({"target_file", "host_file"})
HEADER_PLACEHOLDERS = frozenset({"header", "cookie"})


def _required_text(value: object, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{location} 必须是非空字符串")
    return value.strip()


def _load_arguments(
    value: object,
    location: str,
    allowed_placeholders: frozenset[str],
    allow_empty: bool = False,
) -> tuple[str, ...]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise ValueError(f"{location} 必须是非空字符串数组")
    if any(not isinstance(argument, str) for argument in value):
        raise ValueError(f"{location} 中的每个参数都必须是字符串")
    if any(
        "\x00" in argument or "\r" in argument or "\n" in argument
        for argument in value
    ):
        raise ValueError(f"{location} 不能包含 NUL 或换行字符")

    arguments = tuple(value)
    placeholders = {
        placeholder
        for argument in arguments
        for placeholder in PLACEHOLDER_PATTERN.findall(argument)
    }
    unknown = placeholders - allowed_placeholders
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ValueError(f"{location} 使用了未知占位符：{names}")
    return arguments


def load_tools(config: dict[str, Any]) -> dict[str, Tool]:
    """从 config.json 加载工具；新增配置项即可自动注册模块。"""
    raw_tools = config.get("tools")
    if not isinstance(raw_tools, dict) or not raw_tools:
        raise ValueError("config.json 的 tools 必须是非空对象")

    tools: dict[str, Tool] = {}
    modules: set[str] = set()
    for tool_id, raw_tool in raw_tools.items():
        if not isinstance(tool_id, str) or not TOOL_ID_PATTERN.fullmatch(tool_id):
            raise ValueError(f"工具 ID 不合法：{tool_id!r}")
        location = f"tools.{tool_id}"
        if not isinstance(raw_tool, dict):
            raise ValueError(f"{location} 必须是对象")
        enabled = raw_tool.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ValueError(f"{location}.enabled 必须是布尔值")
        if not enabled:
            continue

        validate_program_config(raw_tool, location)
        _required_text(raw_tool.get("encoding", "utf-8"), f"{location}.encoding")
        if raw_tool.get("working_directory") is not None:
            _required_text(
                raw_tool.get("working_directory"),
                f"{location}.working_directory",
            )
        if not isinstance(raw_tool.get("interactive", False), bool):
            raise ValueError(f"{location}.interactive 必须是布尔值")
        if not isinstance(raw_tool.get("native_terminal", False), bool):
            raise ValueError(f"{location}.native_terminal 必须是布尔值")
        if not isinstance(raw_tool.get("preserve_color", False), bool):
            raise ValueError(f"{location}.preserve_color 必须是布尔值")
        launch_only = raw_tool.get("launch_only", False)
        if not isinstance(launch_only, bool):
            raise ValueError(f"{location}.launch_only 必须是布尔值")
        run_as_admin = raw_tool.get("run_as_admin", False)
        if not isinstance(run_as_admin, bool):
            raise ValueError(f"{location}.run_as_admin 必须是布尔值")
        if run_as_admin and not launch_only:
            raise ValueError(f"{location}.run_as_admin 仅适用于 launch_only 工具")
        startup_timeout = raw_tool.get("startup_timeout", 2.0)
        if (
            isinstance(startup_timeout, bool)
            or not isinstance(startup_timeout, (int, float))
            or not 0 <= startup_timeout <= 30
        ):
            raise ValueError(f"{location}.startup_timeout 必须是 0 到 30 之间的数字")
        if "startup_timeout" in raw_tool and not launch_only:
            raise ValueError(f"{location}.startup_timeout 仅适用于 launch_only 工具")
        required_files = raw_tool.get("required_files", [])
        if not isinstance(required_files, list) or any(
            not isinstance(item, str) or not item.strip() for item in required_files
        ):
            raise ValueError(f"{location}.required_files 必须是字符串数组")
        module = _required_text(
            raw_tool.get("module", f"scanner/{tool_id}"), f"{location}.module"
        )
        console_mode = _required_text(
            raw_tool.get("console_mode"), f"{location}.console_mode"
        ).lower()
        description = _required_text(
            raw_tool.get("description", tool_id), f"{location}.description"
        )
        header_arguments = (
            _load_arguments(
                raw_tool.get("header_args"),
                f"{location}.header_args",
                HEADER_PLACEHOLDERS,
            )
            if raw_tool.get("header_args") is not None
            else None
        )
        cookie_arguments = (
            _load_arguments(
                raw_tool.get("cookie_args"),
                f"{location}.cookie_args",
                HEADER_PLACEHOLDERS,
            )
            if raw_tool.get("cookie_args") is not None
            else None
        )
        if header_arguments is not None and not any(
            "{header}" in argument for argument in header_arguments
        ):
            raise ValueError(f"{location}.header_args 必须包含 {{header}}")
        if cookie_arguments is not None and not any(
            "{cookie}" in argument for argument in cookie_arguments
        ):
            raise ValueError(f"{location}.cookie_args 必须包含 {{cookie}}")
        if module in modules:
            raise ValueError(f"模块名称重复：{module}")
        modules.add(module)
        raw_modes = raw_tool.get("modes")
        if not isinstance(raw_modes, dict) or not raw_modes:
            raise ValueError(f"{location}.modes 必须是非空对象")
        modes: list[TestMode] = []
        marked_default_modes: list[str] = []
        for mode_id, raw_mode in raw_modes.items():
            mode_location = f"{location}.modes.{mode_id}"
            if not isinstance(mode_id, str) or not TOOL_ID_PATTERN.fullmatch(mode_id):
                raise ValueError(f"测试方式 ID 不合法：{mode_id!r}")
            if not isinstance(raw_mode, dict):
                raise ValueError(f"{mode_location} 必须是对象")
            is_default = raw_mode.get("default", False)
            if not isinstance(is_default, bool):
                raise ValueError(f"{mode_location}.default 必须是布尔值")
            if is_default:
                marked_default_modes.append(mode_id)
            requires_target = raw_mode.get("requires_target", not launch_only)
            if not isinstance(requires_target, bool):
                raise ValueError(f"{mode_location}.requires_target 必须是布尔值")
            if launch_only and requires_target:
                raise ValueError(
                    f"{mode_location}.requires_target 对 launch_only 工具必须为 false"
                )
            argument_placeholders = (
                frozenset()
                if launch_only
                else ALLOWED_PLACEHOLDERS
                if requires_target
                else frozenset({"output_dir"})
            )
            modes.append(
                TestMode(
                    id=mode_id,
                    name=_required_text(
                        raw_mode.get("name", mode_id), f"{mode_location}.name"
                    ),
                    description=_required_text(
                        raw_mode.get("description", mode_id),
                        f"{mode_location}.description",
                    ),
                    requires_target=requires_target,
                    arguments=_load_arguments(
                        raw_mode.get("args"),
                        f"{mode_location}.args",
                        argument_placeholders,
                        allow_empty=launch_only or not requires_target,
                    ),
                    list_arguments=(
                        _load_arguments(
                            raw_mode.get("list_args"),
                            f"{mode_location}.list_args",
                            ALLOWED_PLACEHOLDERS | LIST_PLACEHOLDERS,
                        )
                        if raw_mode.get("list_args") is not None
                        else None
                    ),
                )
            )

        if len(marked_default_modes) > 1:
            raise ValueError(
                f"{location}.modes 最多只能有一个模式配置 default: true"
            )
        configured_default = raw_tool.get("default_mode")
        if marked_default_modes:
            default_mode = marked_default_modes[0]
            if configured_default is not None:
                legacy_default = _required_text(
                    configured_default, f"{location}.default_mode"
                )
                if legacy_default != default_mode:
                    raise ValueError(
                        f"{location}.default_mode 与 modes.{default_mode}.default 冲突"
                    )
        else:
            default_mode = _required_text(
                configured_default if configured_default is not None else modes[0].id,
                f"{location}.default_mode",
            )
        if default_mode not in {mode.id for mode in modes}:
            raise ValueError(f"{location}.default_mode 未在 modes 中定义：{default_mode}")
        if any(
            (launch_only or not mode.requires_target)
            and mode.list_arguments is not None
            for mode in modes
        ):
            raise ValueError(
                f"{location} 的 launch_only/无需目标模式不能配置 list_args"
            )
        tools[tool_id] = Tool(
            id=tool_id,
            module=module,
            console_mode=console_mode,
            description=description,
            header_arguments=header_arguments,
            cookie_arguments=cookie_arguments,
            launch_only=launch_only,
            run_as_admin=run_as_admin,
            default_mode=default_mode,
            modes=tuple(modes),
        )

    if not tools:
        raise ValueError("config.json 中没有启用的工具")
    return tools


def get_tool(tools: dict[str, Tool], tool_id: str) -> Tool:
    try:
        return tools[tool_id]
    except KeyError as exc:
        raise ValueError(f"未知工具：{tool_id}") from exc


def get_mode(tool: Tool, mode_id: str) -> TestMode:
    for mode in tool.modes:
        if mode.id == mode_id:
            return mode
    raise ValueError(f"工具 {tool.id!r} 不支持测试方式：{mode_id}")


from tooling.arguments import build_arguments
