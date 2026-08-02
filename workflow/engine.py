"""配置驱动的组合测试流程。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from execution.runner import RunSession, Runner
from tooling.registry import (
    TOOL_ID_PATTERN,
    TargetInput,
    Tool,
    build_arguments,
    get_mode,
    get_tool,
)
from console.ui import error, warning


@dataclass(frozen=True)
class WorkflowStep:
    tool_id: str
    mode_id: str


@dataclass(frozen=True)
class WorkflowMode:
    id: str
    name: str
    description: str
    steps: tuple[WorkflowStep, ...]


@dataclass(frozen=True)
class Workflow:
    id: str
    module: str
    console_mode: str
    description: str
    default_mode: str
    modes: tuple[WorkflowMode, ...]


def _required_text(value: object, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{location} 必须是非空字符串")
    return value.strip()


def load_workflows(
    config: dict[str, Any], tools: dict[str, Tool]
) -> dict[str, Workflow]:
    raw_workflows = config.get("workflows", {})
    if not isinstance(raw_workflows, dict):
        raise ValueError("config.json 的 workflows 必须是对象")

    workflows: dict[str, Workflow] = {}
    tool_modules = {tool.module for tool in tools.values()}
    modules: set[str] = set()
    for workflow_id, raw_workflow in raw_workflows.items():
        if not isinstance(workflow_id, str) or not TOOL_ID_PATTERN.fullmatch(workflow_id):
            raise ValueError(f"流程 ID 不合法：{workflow_id!r}")
        location = f"workflows.{workflow_id}"
        if not isinstance(raw_workflow, dict):
            raise ValueError(f"{location} 必须是对象")
        if raw_workflow.get("enabled", True) is False:
            continue

        module = _required_text(
            raw_workflow.get("module", f"workflow/{workflow_id}"),
            f"{location}.module",
        )
        console_mode = _required_text(
            raw_workflow.get("console_mode"), f"{location}.console_mode"
        ).lower()
        description = _required_text(
            raw_workflow.get("description", workflow_id),
            f"{location}.description",
        )
        if module in modules or module in tool_modules:
            raise ValueError(f"模块名称重复：{module}")
        modules.add(module)
        raw_modes = raw_workflow.get("modes")
        if not isinstance(raw_modes, dict) or not raw_modes:
            raise ValueError(f"{location}.modes 必须是非空对象")
        modes: list[WorkflowMode] = []
        marked_default_modes: list[str] = []
        for mode_id, raw_mode in raw_modes.items():
            mode_location = f"{location}.modes.{mode_id}"
            if not isinstance(mode_id, str) or not TOOL_ID_PATTERN.fullmatch(mode_id):
                raise ValueError(f"流程方式 ID 不合法：{mode_id!r}")
            if not isinstance(raw_mode, dict):
                raise ValueError(f"{mode_location} 必须是对象")
            is_default = raw_mode.get("default", False)
            if not isinstance(is_default, bool):
                raise ValueError(f"{mode_location}.default 必须是布尔值")
            if is_default:
                marked_default_modes.append(mode_id)
            raw_steps = raw_mode.get("steps")
            if not isinstance(raw_steps, list) or not raw_steps:
                raise ValueError(f"{mode_location}.steps 必须是非空数组")

            steps: list[WorkflowStep] = []
            for index, raw_step in enumerate(raw_steps):
                step_location = f"{mode_location}.steps[{index}]"
                if not isinstance(raw_step, dict):
                    raise ValueError(f"{step_location} 必须是对象")
                tool_id = _required_text(
                    raw_step.get("tool"), f"{step_location}.tool"
                )
                tool_mode = _required_text(
                    raw_step.get("mode"), f"{step_location}.mode"
                )
                tool = get_tool(tools, tool_id)
                get_mode(tool, tool_mode)
                steps.append(WorkflowStep(tool_id, tool_mode))

            modes.append(
                WorkflowMode(
                    id=mode_id,
                    name=_required_text(
                        raw_mode.get("name", mode_id), f"{mode_location}.name"
                    ),
                    description=_required_text(
                        raw_mode.get("description", mode_id),
                        f"{mode_location}.description",
                    ),
                    steps=tuple(steps),
                )
            )

        if len(marked_default_modes) > 1:
            raise ValueError(
                f"{location}.modes 最多只能有一个模式配置 default: true"
            )
        configured_default = raw_workflow.get("default_mode")
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
        workflows[workflow_id] = Workflow(
            id=workflow_id,
            module=module,
            console_mode=console_mode,
            description=description,
            default_mode=default_mode,
            modes=tuple(modes),
        )
    return workflows


def get_workflow(workflows: dict[str, Workflow], workflow_id: str) -> Workflow:
    try:
        return workflows[workflow_id]
    except KeyError as exc:
        raise ValueError(f"未知流程：{workflow_id}") from exc


def get_workflow_mode(workflow: Workflow, mode_id: str) -> WorkflowMode:
    for mode in workflow.modes:
        if mode.id == mode_id:
            return mode
    raise ValueError(f"流程 {workflow.id!r} 不支持测试方式：{mode_id}")


def workflow_tool_ids(workflow: Workflow) -> set[str]:
    return {
        step.tool_id
        for mode in workflow.modes
        for step in mode.steps
    }


def run_workflow(
    workflow: Workflow,
    mode_id: str,
    tools: dict[str, Tool],
    runner: Runner,
    session: RunSession,
    target: TargetInput,
    headers: tuple[str, ...] = (),
) -> bool:
    mode = get_workflow_mode(workflow, mode_id)
    executed = 0
    all_succeeded = True
    for step in mode.steps:
        if runner.resolve_executable(step.tool_id) is None:
            print(warning(f"[{step.tool_id}] 未安装或路径未配置，跳过。"))
            all_succeeded = False
            continue

        tool = get_tool(tools, step.tool_id)
        step_headers = tuple(
            header
            for header in headers
            if tool.supports_header(header.split(":", 1)[0].strip())
        )
        arguments = build_arguments(
            tool, step.mode_id, target, session.directory, step_headers
        )
        result = runner.run(
            step.tool_id,
            arguments,
            session,
            tool.sensitive_header_values(step_headers),
        )
        executed += 1
        if result.return_code == 130:
            print(
                warning(
                    f"[{step.tool_id}] 流程已由用户强制停止，不再执行后续工具。"
                )
            )
            return False
        if not result.success:
            all_succeeded = False
            print(error(f"[{step.tool_id}] 执行失败，继续下一步。"))

    if executed == 0:
        print(error("流程中没有可执行的工具，请检查 config.json。"))
        return False
    return all_succeeded
