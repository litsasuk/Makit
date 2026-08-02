"""把配置化工具和工作流组织为控制台可浏览的模块目录。"""

from __future__ import annotations

from dataclasses import dataclass

from tooling.registry import TOOL_ID_PATTERN, TestMode, Tool, get_tool
from workflow.engine import (
    Workflow,
    WorkflowMode,
    get_workflow,
    workflow_tool_ids,
)


Mode = TestMode | WorkflowMode


@dataclass(frozen=True)
class ConsoleMode:
    id: str
    name: str
    description: str


@dataclass(frozen=True)
class ModuleEntry:
    name: str
    kind: str
    item_id: str
    console_mode: str
    description: str
    default_mode: str


def load_console_modes(config: dict[str, object]) -> tuple[ConsoleMode, ...]:
    raw_modes = config.get("console_modes")
    if not isinstance(raw_modes, dict) or not raw_modes:
        raise ValueError("config.json 的 console_modes 必须是非空对象")

    modes: list[ConsoleMode] = []
    for mode_id, raw_mode in raw_modes.items():
        if not isinstance(mode_id, str) or not TOOL_ID_PATTERN.fullmatch(mode_id):
            raise ValueError(f"控制台模式 ID 不合法：{mode_id!r}")
        location = f"console_modes.{mode_id}"
        if not isinstance(raw_mode, dict):
            raise ValueError(f"{location} 必须是对象")
        name = raw_mode.get("name")
        description = raw_mode.get("description")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{location}.name 必须是非空字符串")
        if not isinstance(description, str) or not description.strip():
            raise ValueError(f"{location}.description 必须是非空字符串")
        modes.append(ConsoleMode(mode_id, name.strip(), description.strip()))
    return tuple(modes)


def build_modules(
    tools: dict[str, Tool],
    workflows: dict[str, Workflow],
    console_modes: tuple[ConsoleMode, ...],
) -> tuple[ModuleEntry, ...]:
    known_modes = {mode.id for mode in console_modes}
    modules = [
        ModuleEntry(
            tool.module,
            "tool",
            tool.id,
            tool.console_mode,
            tool.description,
            tool.default_mode,
        )
        for tool in tools.values()
    ]
    modules.extend(
        ModuleEntry(
            workflow.module,
            "workflow",
            workflow.id,
            workflow.console_mode,
            workflow.description,
            workflow.default_mode,
        )
        for workflow in workflows.values()
    )
    for module in modules:
        if module.console_mode not in known_modes:
            raise ValueError(
                f"模块 {module.name!r} 引用了未知 console_mode："
                f"{module.console_mode}"
            )
    return tuple(modules)


def modules_for_console_mode(
    modules: tuple[ModuleEntry, ...], mode_id: str
) -> tuple[ModuleEntry, ...]:
    return tuple(module for module in modules if module.console_mode == mode_id)


def modes_for(
    module: ModuleEntry,
    tools: dict[str, Tool],
    workflows: dict[str, Workflow],
) -> tuple[Mode, ...]:
    if module.kind == "tool":
        return get_tool(tools, module.item_id).modes
    return get_workflow(workflows, module.item_id).modes


def module_header_description(
    module: ModuleEntry,
    tools: dict[str, Tool],
    workflows: dict[str, Workflow],
) -> str:
    if module.kind == "tool":
        related_tools = (get_tool(tools, module.item_id),)
    else:
        workflow = get_workflow(workflows, module.item_id)
        related_tools = tuple(
            get_tool(tools, tool_id) for tool_id in workflow_tool_ids(workflow)
        )
    if any(tool.header_arguments is not None for tool in related_tools):
        return "可选；支持 Cookie 及其他 HTTP 请求头"
    if any(tool.cookie_arguments is not None for tool in related_tools):
        return "可选；当前工具仅支持 Cookie"
    return "当前工具不支持自定义请求头"


def module_supports_header_name(
    module: ModuleEntry,
    header_name: str,
    tools: dict[str, Tool],
    workflows: dict[str, Workflow],
) -> bool:
    def tool_supports(tool: Tool) -> bool:
        return tool.supports_header(header_name)

    if module.kind == "tool":
        return tool_supports(get_tool(tools, module.item_id))
    workflow = get_workflow(workflows, module.item_id)
    return any(
        tool_supports(get_tool(tools, tool_id))
        for tool_id in workflow_tool_ids(workflow)
    )
