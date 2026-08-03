"""Makit CLI 入口及配置驱动的类 Metasploit 控制台。"""

from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path

from console.catalog import (
    ConsoleMode,
    Mode,
    ModuleEntry,
    build_modules,
    load_console_modes,
    modes_for,
    module_supports_header_name,
    modules_for_console_mode,
)
from execution.runner import (
    Runner,
    ToolUnavailable,
    create_session,
    format_command,
    load_config,
    parse_command,
)
from console.ui import (
    banner,
    error,
    info,
    muted,
    read_console_input,
    success,
)
from console.headers import (
    normalize_request_header,
    remove_request_header,
    replace_request_header,
)
from console.rendering import display_width, pad_cell, show_table, table_widths
from tooling.registry import (
    TargetInput,
    Tool,
    build_arguments,
    get_mode,
    get_tool,
    load_target_input,
    load_tools,
)
from workflow.engine import (
    Workflow,
    get_workflow,
    get_workflow_mode,
    load_workflows,
    run_workflow,
)


PROJECT_DIR = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parents[1]
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="makit",
        description="配置驱动的安全测试工具调用器（仅用于已授权目标）",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT_DIR / "config.json",
        help="配置文件路径（默认：项目目录/config.json）",
    )
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("tools", help="显示操作模式及其工具")

    run_parser = subparsers.add_parser("run", help="非交互执行单个工具")
    run_parser.add_argument("tool", help="config.json 中的工具 ID")
    run_parser.add_argument(
        "--target", help="已获授权的域名、http/https URL 或 TXT 列表；启动型工具省略"
    )
    run_parser.add_argument("--mode", help="测试方式；省略时使用工具 default_mode")

    workflow_parser = subparsers.add_parser("workflow", help="非交互执行组合流程")
    workflow_parser.add_argument("name", help="config.json 中的流程 ID")
    workflow_parser.add_argument(
        "--target", required=True, help="已获授权的域名、http/https URL 或 TXT 列表"
    )
    workflow_parser.add_argument("--mode", help="流程方式；省略时使用 default_mode")
    return parser


def show_console_modes(console_modes: tuple[ConsoleMode, ...]) -> None:
    show_table(
        "Operation Modes",
        ("#", "Mode", "Description"),
        [
            (index, mode.name, mode.description)
            for index, mode in enumerate(console_modes, start=1)
        ],
    )


def show_tools(
    modules: tuple[ModuleEntry, ...],
    title: str = "Modules",
) -> None:
    rows: list[tuple[object, ...]] = []
    for index, module in enumerate(modules, start=1):
        rows.append(
            (
                index,
                module.name,
                module.description,
            )
        )
    show_table(title, ("#", "Name", "Description"), rows)


def execute_one(
    runner: Runner,
    tools: dict[str, Tool],
    tool_id: str,
    target: TargetInput | None,
    mode_id: str | None,
    headers: tuple[str, ...] = (),
    edit_command: bool = False,
) -> int:
    tool = get_tool(tools, tool_id)
    mode_id = mode_id or tool.default_mode
    selected_mode = get_mode(tool, mode_id)
    if tool.launch_only:
        arguments = list(selected_mode.arguments)
        command = runner.build_command(tool_id, arguments, launch=True)
        if edit_command:
            command, _ = edit_tool_command(command)
        return runner.launch(
            tool_id,
            arguments,
            run_as_admin=tool.run_as_admin,
            command=command,
        )
    if selected_mode.requires_url and target is None:
        raise ValueError("URL 为必填项，请直接输入 URL 后再执行 run")

    session_label = (
        target.session_label if target is not None else f"{tool_id}_{mode_id}"
    )
    session = create_session(runner.output_root, session_label)
    arguments = build_arguments(tool, mode_id, target, session.directory, headers)
    sensitive_values = tool.sensitive_header_values(headers)
    command = runner.build_command(tool_id, arguments)
    if edit_command:
        command, sensitive_values = edit_tool_command(command, sensitive_values)
    result = runner.run(
        tool_id,
        arguments,
        session,
        sensitive_values,
        command=command,
    )
    print(success(f"输出目录：{session.directory}"))
    return result.return_code


def execute_workflow(
    runner: Runner,
    tools: dict[str, Tool],
    workflows: dict[str, Workflow],
    workflow_id: str,
    target: TargetInput,
    mode_id: str | None,
    headers: tuple[str, ...] = (),
) -> int:
    workflow = get_workflow(workflows, workflow_id)
    mode_id = mode_id or workflow.default_mode
    get_workflow_mode(workflow, mode_id)
    session = create_session(runner.output_root, target.session_label)
    success = run_workflow(
        workflow=workflow,
        mode_id=mode_id,
        tools=tools,
        runner=runner,
        session=session,
        target=target,
        headers=headers,
    )
    print(success(f"输出目录：{session.directory}"))
    return 0 if success else 1


def find_module(modules: tuple[ModuleEntry, ...], value: str) -> ModuleEntry:
    value = value.strip().lower()
    if value.isdigit():
        index = int(value)
        if 1 <= index <= len(modules):
            return modules[index - 1]
    matches = [
        module
        for module in modules
        if value in {module.name.lower(), module.item_id.lower()}
    ]
    if len(matches) == 1:
        return matches[0]
    raise ValueError(f"未知模块：{value or '(空)'}，请先执行 show tools")


def find_console_mode(
    console_modes: tuple[ConsoleMode, ...], value: str
) -> ConsoleMode:
    value = value.strip().lower()
    if value.isdigit():
        index = int(value)
        if 1 <= index <= len(console_modes):
            return console_modes[index - 1]
    for mode in console_modes:
        if value in {mode.id.lower(), mode.name.lower()}:
            return mode
    available = "/".join(mode.id for mode in console_modes)
    raise ValueError(f"未知操作模式：{value or '(空)'}，请选择 {available}")


def find_mode(modes: tuple[Mode, ...], value: str) -> Mode:
    value = value.strip().lower()
    if value.isdigit():
        index = int(value)
        if 1 <= index <= len(modes):
            return modes[index - 1]
    for mode in modes:
        if value in {mode.id.lower(), mode.name.lower()}:
            return mode
    raise ValueError(f"不支持的测试方式：{value or '(空)'}")


def show_modes(
    module: ModuleEntry,
    tools: dict[str, Tool],
    workflows: dict[str, Workflow],
) -> None:
    rows: list[tuple[object, ...]] = []
    for index, mode in enumerate(modes_for(module, tools, workflows), start=1):
        rows.append(
            (
                index,
                mode.id,
                mode.description,
            )
        )
    show_table(
        f"Modes ({module.name})",
        ("#", "Name", "Description"),
        rows,
    )


def show_help() -> None:
    headers = ("Command", "Description")
    core_commands: list[tuple[object, ...]] = [
        ("?", "显示帮助菜单"),
        ("help", "显示帮助菜单"),
        ("show modes", "显示配置中的操作模式"),
        ("show tools", "显示当前操作模式下的工具"),
        ("use <编号或名称>", "选择操作模式或工具"),
        ("b / back", "返回上一级"),
        ("q / exit / quit", "退出 Makit"),
    ]
    module_commands: list[tuple[object, ...]] = [
        ("show modes", "显示当前模块的测试方式"),
        ("<域名或URL>", "直接设置目标，裸域名自动补全协议"),
        ("set url <URL或TXT>", "设置 URL 或 UTF-8 TXT 目标列表"),
        ("set mode <编号或名称>", "选择命令预设"),
        ("set header \"Name: Value\"", "添加或替换 HTTP 请求头"),
        ("set cookie \"a=b\"", "设置 Cookie 请求头"),
        ("unset header <名称/all>", "删除一个或全部请求头"),
        ("run", "显示并编辑完整命令，按回车后执行"),
    ]
    shared_widths = table_widths(headers, core_commands + module_commands)
    show_table(
        "Core Commands",
        headers,
        core_commands,
        shared_widths,
    )
    show_table(
        "Module Commands",
        headers,
        module_commands,
        shared_widths,
    )


def parse_console_line(line: str) -> list[str]:
    try:
        parts = shlex.split(line, posix=False)
    except ValueError as exc:
        raise ValueError(f"命令格式错误：{exc}") from exc
    return [
        part[1:-1]
        if len(part) >= 2 and part[0] == part[-1] and part[0] in {'"', "'"}
        else part
        for part in parts
    ]


def edit_tool_command(
    command: list[str], sensitive_values: tuple[str, ...] = ()
) -> tuple[list[str], tuple[str, ...]]:
    """显示可编辑命令，并在解析后恢复被隐藏的请求头值。"""
    display_parts = command.copy()
    secret_tokens: dict[str, str] = {}
    for secret_index, sensitive_value in enumerate(
        dict.fromkeys(sensitive_values), start=1
    ):
        if not sensitive_value:
            continue
        token = f"<redacted:{secret_index}>"
        name, separator, raw_value = sensitive_value.partition(":")
        if separator:
            replacement = f"{name}: {token}"
            restored_value = raw_value.strip()
        else:
            replacement = token
            restored_value = sensitive_value
        changed = False
        for index, argument in enumerate(display_parts):
            if sensitive_value in argument:
                display_parts[index] = argument.replace(sensitive_value, replacement)
                changed = True
        if changed:
            secret_tokens[token] = restored_value

    initial_value = format_command(display_parts)
    print(info("当前工具调用命令如下；可直接修改或追加参数，按回车后执行。"))
    edited_line = read_console_input("command > ", initial_value=initial_value)
    edited_command = parse_command(edited_line)
    edited_sensitive_values: list[str] = []
    for index, argument in enumerate(edited_command):
        restored = argument
        contains_secret = False
        for token, value in secret_tokens.items():
            if token in restored:
                contains_secret = True
            restored = restored.replace(token, value)
        edited_command[index] = restored
        if contains_secret:
            edited_sensitive_values.append(restored)
    return edited_command, tuple(edited_sensitive_values)


def show_target_value(target: TargetInput) -> None:
    if target.is_list:
        print(success(f"URL => {target.display_value}（{len(target.urls)} 个目标）"))
    else:
        print(success(f"URL => {target.display_value}"))


def show_banner() -> None:
    print(banner(
        r"""
 __  __    _    _  _____ _____
|  \/  |  / \  | |/ /_ _|_   _|
| |\/| | / _ \ | ' / | |  | |
| |  | |/ ___ \| . \ | |  | |
|_|  |_/_/   \_\_|\_\___| |_|
""".strip("\n")
    ))
    print(muted("配置驱动的安全测试控制台 · 仅用于已明确授权的目标"))


def interactive_console(
    runner: Runner,
    tools: dict[str, Tool],
    workflows: dict[str, Workflow],
    modules: tuple[ModuleEntry, ...],
    console_modes: tuple[ConsoleMode, ...],
) -> int:
    show_banner()
    show_console_modes(console_modes)
    available_mode_ids = "/".join(mode.id for mode in console_modes)
    print(info(f"请先选择操作模式；可直接输入编号或 {available_mode_ids}。"))

    active_console_mode: ConsoleMode | None = None
    selected: ModuleEntry | None = None
    target: TargetInput | None = None
    mode: str | None = None
    headers: tuple[str, ...] = ()
    first_prompt = True
    while True:
        if first_prompt:
            first_prompt = False
        else:
            print()

        if selected is not None and active_console_mode is not None:
            selected_path = (
                selected.name
                if selected.name.startswith(f"{active_console_mode.id}/")
                else f"{active_console_mode.id}/{selected.name}"
            )
            prompt = f"makit ({selected_path}) > "
        elif active_console_mode is not None:
            prompt = f"makit ({active_console_mode.id}) > "
        else:
            prompt = "makit > "
        try:
            parts = parse_console_line(read_console_input(prompt).strip())
        except (EOFError, KeyboardInterrupt):
            print(info("退出 Makit。"))
            return 0
        except ValueError as exc:
            print(error(exc))
            continue
        if not parts:
            continue

        command, arguments = parts[0].lower(), parts[1:]
        try:
            if command in {"q", "exit", "quit"}:
                return 0
            if command in {"help", "?"}:
                show_help()
                continue
            if command in {"b", "back"}:
                if selected is not None:
                    selected, target, mode = None, None, None
                    headers = ()
                    assert active_console_mode is not None
                    available_modules = modules_for_console_mode(
                        modules, active_console_mode.id
                    )
                    show_tools(
                        available_modules,
                        f"{active_console_mode.name} Modules",
                    )
                elif active_console_mode is not None:
                    active_console_mode = None
                    show_console_modes(console_modes)
                else:
                    show_console_modes(console_modes)
                continue
            if command.isdigit() and not arguments:
                if active_console_mode is None:
                    active_console_mode = find_console_mode(console_modes, command)
                    available_modules = modules_for_console_mode(
                        modules, active_console_mode.id
                    )
                    show_tools(
                        available_modules,
                        f"{active_console_mode.name} Modules",
                    )
                else:
                    available_modules = modules_for_console_mode(
                        modules, active_console_mode.id
                    )
                    selected = find_module(available_modules, command)
                    target, mode = None, selected.default_mode
                    headers = ()
                    show_modes(selected, tools, workflows)
                continue
            if command == "use":
                if len(arguments) != 1:
                    raise ValueError("用法：use <模式/工具编号或名称>")
                if active_console_mode is None:
                    active_console_mode = find_console_mode(
                        console_modes, arguments[0]
                    )
                    available_modules = modules_for_console_mode(
                        modules, active_console_mode.id
                    )
                    show_tools(
                        available_modules,
                        f"{active_console_mode.name} Modules",
                    )
                else:
                    available_modules = modules_for_console_mode(
                        modules, active_console_mode.id
                    )
                    selected = find_module(available_modules, arguments[0])
                    target, mode = None, selected.default_mode
                    headers = ()
                    show_modes(selected, tools, workflows)
                continue
            if command == "show":
                subject = arguments[0].lower() if len(arguments) == 1 else ""
                if subject in {"tools", "modules"}:
                    if active_console_mode is None:
                        show_console_modes(console_modes)
                    else:
                        available_modules = modules_for_console_mode(
                            modules, active_console_mode.id
                        )
                        show_tools(
                            available_modules,
                            f"{active_console_mode.name} Modules",
                        )
                elif subject == "modes":
                    if selected:
                        show_modes(selected, tools, workflows)
                    else:
                        show_console_modes(console_modes)
                else:
                    raise ValueError("用法：show tools 或 show modes")
                continue
            if command == "set":
                if selected is None:
                    raise ValueError("请先使用 use <编号或名称> 选择模块")
                if len(arguments) != 2:
                    raise ValueError(
                        "用法：set url/mode <值>；set header \"Name: Value\"；"
                        "set cookie \"a=b\""
                    )
                option, value = arguments[0].lower(), arguments[1]
                if option in {"url", "target"}:
                    target = load_target_input(value, PROJECT_DIR)
                    show_target_value(target)
                elif option == "mode":
                    mode = find_mode(modes_for(selected, tools, workflows), value).id
                    print(success(f"MODE => {mode}"))
                elif option in {"header", "cookie"}:
                    header = normalize_request_header(
                        f"Cookie: {value}" if option == "cookie" else value
                    )
                    header_name = header.split(":", 1)[0]
                    if not module_supports_header_name(
                        selected, header_name, tools, workflows
                    ):
                        raise ValueError(
                            f"当前工具不支持请求头：{header_name}"
                        )
                    headers = replace_request_header(headers, header)
                    print(
                        success(
                            f"HEADER => {header_name}（已配置，共 {len(headers)} 个）"
                        )
                    )
                else:
                    raise ValueError("只允许设置 URL、MODE、HEADER 和 COOKIE")
                continue
            if command == "unset":
                if selected is None:
                    raise ValueError("请先选择工具")
                if len(arguments) != 2 or arguments[0].lower() != "header":
                    raise ValueError("用法：unset header <名称或 all>")
                headers = remove_request_header(headers, arguments[1])
                print(success(f"HEADERS => {len(headers)} configured"))
                continue
            if command == "run":
                if selected is None:
                    raise ValueError("请先使用 use <编号或名称> 选择模块")
                if selected.kind == "tool":
                    selected_tool = get_tool(tools, selected.item_id)
                    execute_one(
                        runner,
                        tools,
                        selected.item_id,
                        target,
                        mode,
                        headers,
                        edit_command=True,
                    )
                    if selected_tool.launch_only:
                        selected, target, mode = None, None, None
                        headers = ()
                        assert active_console_mode is not None
                        available_modules = modules_for_console_mode(
                            modules, active_console_mode.id
                        )
                        show_tools(
                            available_modules,
                            f"{active_console_mode.name} Modules",
                        )
                else:
                    if target is None or mode is None:
                        raise ValueError("URL 为必填项，请直接输入 URL")
                    execute_workflow(
                        runner,
                        tools,
                        workflows,
                        selected.item_id,
                        target,
                        mode,
                        headers,
                    )
                continue
            if selected is not None and len(parts) == 1:
                target = load_target_input(parts[0], PROJECT_DIR)
                show_target_value(target)
                continue
            if active_console_mode is None and len(parts) == 1:
                active_console_mode = find_console_mode(console_modes, command)
                available_modules = modules_for_console_mode(
                    modules, active_console_mode.id
                )
                show_tools(
                    available_modules,
                    f"{active_console_mode.name} Modules",
                )
                continue
            if active_console_mode is not None and len(parts) == 1:
                available_modules = modules_for_console_mode(
                    modules, active_console_mode.id
                )
                selected = find_module(available_modules, command)
                target, mode = None, selected.default_mode
                headers = ()
                show_modes(selected, tools, workflows)
                continue
            raise ValueError(f"未知命令：{command}，输入 help 查看帮助")
        except (OSError, ToolUnavailable, ValueError) as exc:
            print(error(f"[-] {exc}"))


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        console_modes = load_console_modes(config)
        tools = load_tools(config)
        workflows = load_workflows(config, tools)
        modules = build_modules(tools, workflows, console_modes)
        runner = Runner(PROJECT_DIR, config)
        if args.command is None:
            return interactive_console(
                runner, tools, workflows, modules, console_modes
            )
        if args.command == "tools":
            show_console_modes(console_modes)
            for console_mode in console_modes:
                available_modules = modules_for_console_mode(
                    modules, console_mode.id
                )
                show_tools(
                    available_modules,
                    f"{console_mode.name} Modules",
                )
            return 0
        if args.command == "run":
            target = (
                load_target_input(args.target, PROJECT_DIR) if args.target else None
            )
            return execute_one(runner, tools, args.tool, target, args.mode)
        if args.command == "workflow":
            target = load_target_input(args.target, PROJECT_DIR)
            return execute_workflow(
                runner, tools, workflows, args.name, target, args.mode
            )
    except (OSError, ToolUnavailable, ValueError) as exc:
        print(error(f"错误：{exc}", sys.stderr), file=sys.stderr)
        return 1

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
