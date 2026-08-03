"""外部进程执行和运行目录管理。

本模块不了解任何具体工具，只接受已经生成好的参数列表。
因此上层 CLI、工具定义和工作流都可以独立变化。
"""

from __future__ import annotations

import ctypes
import json
import os
import queue
import shlex
import signal
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any
from ctypes import wintypes

from execution.gui import INTERNAL_LAUNCH_FLAG, launch_gui
from execution.programs import ProgramResolver, ResolvedProgram, ToolUnavailable
from execution.sessions import RunResult, RunSession, create_session
from configuration import load_config
from console.ui import error, info, success, warning


def format_command(command: list[str]) -> str:
    """将参数数组格式化为当前平台可编辑的命令行。"""
    if os.name == "nt":
        return subprocess.list2cmdline(command)
    return shlex.join(command)


def parse_command(command_line: str) -> list[str]:
    """将用户编辑后的命令安全解析为参数数组，不经过 Shell。"""
    if not command_line.strip():
        raise ValueError("工具调用命令不能为空")
    if any(character in command_line for character in ("\x00", "\r", "\n")):
        raise ValueError("工具调用命令不能包含 NUL 或换行字符")
    if os.name != "nt":
        try:
            return shlex.split(command_line, posix=True)
        except ValueError as exc:
            raise ValueError(f"工具调用命令格式错误：{exc}") from exc

    argv = ctypes.POINTER(wintypes.LPWSTR)()
    argument_count = ctypes.c_int()
    command_line_to_argv = ctypes.windll.shell32.CommandLineToArgvW
    command_line_to_argv.argtypes = [
        wintypes.LPCWSTR,
        ctypes.POINTER(ctypes.c_int),
    ]
    command_line_to_argv.restype = ctypes.POINTER(wintypes.LPWSTR)
    argv = command_line_to_argv(command_line, ctypes.byref(argument_count))
    if not argv:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return [argv[index] for index in range(argument_count.value)]
    finally:
        ctypes.windll.kernel32.LocalFree(argv)


class _ShellExecuteInfoW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("fMask", wintypes.ULONG),
        ("hwnd", wintypes.HWND),
        ("lpVerb", wintypes.LPCWSTR),
        ("lpFile", wintypes.LPCWSTR),
        ("lpParameters", wintypes.LPCWSTR),
        ("lpDirectory", wintypes.LPCWSTR),
        ("nShow", ctypes.c_int),
        ("hInstApp", wintypes.HINSTANCE),
        ("lpIDList", wintypes.LPVOID),
        ("lpClass", wintypes.LPCWSTR),
        ("hkeyClass", wintypes.HKEY),
        ("dwHotKey", wintypes.DWORD),
        ("hIcon", wintypes.HANDLE),
        ("hProcess", wintypes.HANDLE),
    ]


def _launch_elevated_windows(
    executable: Path,
    parameters: tuple[str, ...],
    working_directory: Path,
) -> None:
    """通过 Windows UAC 启动隐藏助手，并等待助手进程退出。"""
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    shell_execute = shell32.ShellExecuteExW
    shell_execute.argtypes = [ctypes.POINTER(_ShellExecuteInfoW)]
    shell_execute.restype = wintypes.BOOL

    shell_info = _ShellExecuteInfoW()
    shell_info.cbSize = ctypes.sizeof(shell_info)
    shell_info.fMask = 0x00000040 | 0x00000100  # NOCLOSEPROCESS | NOASYNC
    shell_info.lpVerb = "runas"
    shell_info.lpFile = str(executable)
    shell_info.lpParameters = subprocess.list2cmdline(parameters)
    shell_info.lpDirectory = str(working_directory)
    shell_info.nShow = 0  # 隐藏提权助手窗口，目标 GUI 不受影响。

    if not shell_execute(ctypes.byref(shell_info)):
        error_code = ctypes.get_last_error()
        if error_code == 1223:
            raise PermissionError("管理员权限请求已取消或被拒绝")
        raise ctypes.WinError(error_code)
    if not shell_info.hProcess:
        raise OSError("管理员启动成功，但未获得启动助手的进程句柄")

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    wait_for_single_object = kernel32.WaitForSingleObject
    wait_for_single_object.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    wait_for_single_object.restype = wintypes.DWORD
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL

    try:
        while True:
            wait_result = wait_for_single_object(shell_info.hProcess, 100)
            if wait_result == 0:  # WAIT_OBJECT_0
                break
            if wait_result != 0x00000102:  # WAIT_TIMEOUT
                raise OSError(
                    f"等待 GUI 启动助手结束失败，WaitForSingleObject 返回 {wait_result}"
                )
    finally:
        close_handle(shell_info.hProcess)


class Runner:
    """查找并运行外部工具，实时转发 stdout/stderr。"""

    def __init__(self, project_dir: Path, config: dict[str, Any]) -> None:
        self.project_dir = project_dir
        self.config = config
        self.programs = ProgramResolver(project_dir)
        output_value = config.get("output_dir", "output")
        if not isinstance(output_value, str) or not output_value.strip():
            raise ValueError("output_dir 必须是非空字符串")
        configured_output = Path(os.path.expandvars(output_value.strip()))
        self.output_root = (
            configured_output
            if configured_output.is_absolute()
            else project_dir / configured_output
        )

    def resolve_executable(self, tool_id: str) -> Path | None:
        tool_config = self.config.get("tools", {}).get(tool_id, {})
        if not isinstance(tool_config, dict):
            return None
        resolved = self.programs.resolve_optional(tool_id, tool_config)
        return resolved.executable if resolved is not None else None

    def resolve_command(self, tool_id: str) -> list[str]:
        resolved, _ = self._resolve_plan(tool_id, launch=False)
        return list(resolved.command)

    def build_command(
        self,
        tool_id: str,
        arguments: list[str] | None = None,
        *,
        launch: bool = False,
    ) -> list[str]:
        resolved, _ = self._resolve_plan(tool_id, launch=launch)
        return [*resolved.command, *map(str, arguments or ())]

    def _resolve_plan(
        self, tool_id: str, *, launch: bool
    ) -> tuple[ResolvedProgram, Path]:
        """一次完成程序和工作目录解析，供 CLI/GUI 共用。"""
        tool_config = self.config.get("tools", {}).get(tool_id, {})
        if not isinstance(tool_config, dict):
            raise ToolUnavailable(f"工具 {tool_id!r} 未配置")
        resolved = self.programs.resolve_required(tool_id, tool_config)
        working_directory = self.programs.working_directory(
            tool_id, tool_config, resolved, launch=launch
        )
        return resolved, working_directory

    def launch(
        self,
        tool_id: str,
        arguments: list[str] | None = None,
        run_as_admin: bool = False,
        command: list[str] | None = None,
    ) -> int:
        """按配置参数启动独立 GUI 工具，启动完成后立即返回。"""
        resolved, working_directory = self._resolve_plan(tool_id, launch=True)
        command = command or [*resolved.command, *map(str, arguments or ())]
        if not command:
            raise ValueError("工具调用命令不能为空")
        tool_config = self.config.get("tools", {}).get(tool_id, {})
        encoding = tool_config.get("encoding", "utf-8")
        startup_timeout = float(tool_config.get("startup_timeout", 2.0))

        print(info(f"[{tool_id}] 正在启动图形界面……"))
        if run_as_admin:
            if os.name != "nt":
                raise OSError("run_as_admin 仅支持 Windows")
            launcher = Path(sys.executable).resolve()
            launcher_parameters: tuple[str, ...]
            if getattr(sys, "frozen", False):
                launcher_parameters = (INTERNAL_LAUNCH_FLAG,)
            else:
                entry_script = self.project_dir / "main.py"
                if not entry_script.is_file():
                    raise OSError(f"缺少主程序入口：{entry_script}")
                launcher_parameters = (str(entry_script), INTERNAL_LAUNCH_FLAG)
            descriptor, status_name = tempfile.mkstemp(
                prefix="makit-gui-", suffix=".json"
            )
            os.close(descriptor)
            status_file = Path(status_name)
            try:
                _launch_elevated_windows(
                    launcher,
                    (
                        *launcher_parameters,
                        str(status_file),
                        str(working_directory),
                        str(encoding),
                        str(startup_timeout),
                        *command,
                    ),
                    self.project_dir,
                )
                try:
                    launch_result = json.loads(
                        status_file.read_text(encoding="utf-8")
                    )
                except (json.JSONDecodeError, OSError) as exc:
                    raise OSError(f"无法读取 GUI 启动结果：{exc}") from exc
            finally:
                status_file.unlink(missing_ok=True)
        else:
            launch_result = launch_gui(
                command,
                working_directory,
                str(encoding),
                startup_timeout,
            )

        if not isinstance(launch_result, dict) or not launch_result.get("ok"):
            return_code = launch_result.get("return_code")
            details = launch_result.get("output") or launch_result.get("error")
            message = f"工具 {tool_id!r} 图形界面启动失败"
            if return_code is not None:
                message += f"（退出码 {return_code}）"
            if details:
                message += f"：\n{details}"
            raise ToolUnavailable(message)
        print(success(f"[{tool_id}] 图形界面已启动。"))
        return 0

    def run(
        self,
        tool_id: str,
        arguments: list[str],
        session: RunSession,
        sensitive_values: tuple[str, ...] = (),
        command: list[str] | None = None,
    ) -> RunResult:
        resolved, working_directory = self._resolve_plan(tool_id, launch=False)
        command = command or [*resolved.command, *map(str, arguments)]
        if not command:
            raise ValueError("工具调用命令不能为空")
        display_parts = command.copy()
        for index, argument in enumerate(display_parts):
            redacted = argument
            for sensitive_value in sorted(sensitive_values, key=len, reverse=True):
                if not sensitive_value or sensitive_value not in redacted:
                    continue
                name, separator, _ = sensitive_value.partition(":")
                replacement = (
                    f"{name}: <redacted>" if separator else "<redacted>"
                )
                redacted = redacted.replace(sensitive_value, replacement)
            display_parts[index] = redacted
        display_command = format_command(display_parts)
        output_file = session.directory / f"{tool_id}.log"

        print(info(f"[{tool_id}] {display_command}"))
        with session.commands_file.open("a", encoding="utf-8") as commands_log:
            commands_log.write(display_command + "\n")

        creation_flags = 0
        if os.name == "nt":
            creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP

        tool_config = self.config.get("tools", {}).get(tool_id, {})
        encoding = tool_config.get("encoding", "utf-8")
        # CLI 默认继承当前终端输入；是否读取输入由工具自身决定。
        interactive = tool_config.get("interactive", True)
        preserve_color = tool_config.get("preserve_color", True)
        native_terminal = tool_config.get("native_terminal", False)
        if not isinstance(preserve_color, bool):
            raise ValueError(f"工具 {tool_id!r} 的 preserve_color 必须是布尔值")
        if not isinstance(native_terminal, bool):
            raise ValueError(f"工具 {tool_id!r} 的 native_terminal 必须是布尔值")

        child_environment = None
        if preserve_color:
            child_environment = os.environ.copy()
            child_environment["MAKIT_FORCE_COLOR"] = "1"
            child_environment["FORCE_COLOR"] = "1"
            child_environment["CLICOLOR_FORCE"] = "1"
            child_environment.setdefault("TERM", "xterm-256color")

        if native_terminal:
            output_file.write_text(
                "该工具使用 native_terminal 直接继承控制台；"
                "原生终端输出未写入此日志。\n",
                encoding="utf-8",
            )
            process = subprocess.Popen(
                command,
                cwd=working_directory,
                stdout=None,
                stderr=None,
                stdin=None if interactive else subprocess.DEVNULL,
                env=child_environment,
                shell=False,
                creationflags=creation_flags,
                start_new_session=os.name != "nt",
            )
            try:
                while True:
                    try:
                        return_code = process.wait(timeout=0.1)
                        break
                    except subprocess.TimeoutExpired:
                        continue
            except KeyboardInterrupt:
                print(
                    "\n"
                    + warning(
                        f"[{tool_id}] 收到 Ctrl+C，正在强制结束工具及其子进程……"
                    )
                )
                self._terminate_process(process)
                print(warning(f"[{tool_id}] 已强制结束。"))
                return RunResult(tool_id, 130, output_file)
            except BaseException:
                self._terminate_process(process)
                raise

            status = success if return_code == 0 else error
            print(status(f"[{tool_id}] 结束，退出码：{return_code}"))
            return RunResult(tool_id, return_code, output_file)

        process = subprocess.Popen(
            command,
            cwd=working_directory,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            # 默认继承当前终端输入；显式关闭交互时使用 DEVNULL。
            stdin=None if interactive else subprocess.DEVNULL,
            text=True,
            encoding=encoding,
            errors="replace",
            env=child_environment,
            shell=False,
            creationflags=creation_flags,
            # POSIX 下单独建立会话，停止时才能连同工具派生的子进程一起结束。
            start_new_session=os.name != "nt",
        )

        # Windows 上，主线程若直接阻塞在管道 read()，控制台虽然已经收到
        # Ctrl+C，Python 也可能要等到工具再次输出后才能抛出 KeyboardInterrupt。
        # 让后台线程负责阻塞读取，主线程定时从队列取数据，便可及时处理中断。
        output_queue: queue.Queue[str | BaseException | object] = queue.Queue()
        output_finished = object()

        def read_output() -> None:
            try:
                assert process.stdout is not None
                # TextIOWrapper 默认会把独立的 \r 转换成 \n，导致工具用 \r
                # 刷新的进度条在 Makit 中变成一行一条。保留原始换行后，交互
                # 工具可直接原地刷新，非交互工具则交给下方进度行分支处理。
                process.stdout.reconfigure(newline="")
                if interactive:
                    while True:
                        character = process.stdout.read(1)
                        if character == "":
                            break
                        output_queue.put(character)
                else:
                    for line in process.stdout:
                        output_queue.put(line)
            except BaseException as exc:
                output_queue.put(exc)
            finally:
                output_queue.put(output_finished)

        output_reader = threading.Thread(
            target=read_output,
            name=f"makit-{tool_id}-output",
            daemon=True,
        )
        output_reader.start()

        try:
            with output_file.open("w", encoding="utf-8") as output_log:
                progress_line: str | None = None
                progress_width = 0
                while True:
                    try:
                        item = output_queue.get(timeout=0.1)
                    except queue.Empty:
                        continue
                    if item is output_finished:
                        break
                    if isinstance(item, BaseException):
                        raise item

                    if interactive:
                        # input() 提示通常没有换行。逐字符转发可以在工具等待
                        # y/n 输入之前立即显示提示，同时仍完整保存运行日志。
                        sys.stdout.write(item)
                        sys.stdout.flush()
                        output_log.write(item)
                        output_log.flush()
                    else:
                        line = item
                        if line.endswith("\r") and not line.endswith("\r\n"):
                            current = line[:-1]
                            padding = " " * max(0, progress_width - len(current))
                            sys.stdout.write(f"\r{current}{padding}")
                            sys.stdout.flush()
                            progress_line = current
                            progress_width = len(current)
                            continue

                        if progress_line is not None:
                            sys.stdout.write("\r" + " " * progress_width + "\r")
                            progress_line = None
                            progress_width = 0

                        print(line, end="", flush=True)
                        output_log.write(line.replace("\r\n", "\n"))
                        output_log.flush()

                # 进程若以动态进度行结束，只在日志中保存最终状态一次。
                if not interactive and progress_line is not None:
                    sys.stdout.write("\n")
                    output_log.write(progress_line + "\n")
            return_code = process.wait()
        except KeyboardInterrupt:
            print(
                "\n"
                + warning(
                    f"[{tool_id}] 收到 Ctrl+C，正在强制结束工具及其子进程……"
                )
            )
            self._terminate_process(process)
            output_reader.join(timeout=1)
            print(warning(f"[{tool_id}] 已强制结束。"))
            return RunResult(tool_id, 130, output_file)
        except BaseException:
            # 日志写入、输出解码等异常也不能让外部工具留在后台运行。
            self._terminate_process(process)
            output_reader.join(timeout=1)
            raise

        output_reader.join(timeout=1)
        if process.stdout is not None:
            process.stdout.close()

        status = success if return_code == 0 else error
        print(status(f"[{tool_id}] 结束，退出码：{return_code}"))
        return RunResult(tool_id, return_code, output_file)

    @staticmethod
    def _terminate_process(process: subprocess.Popen[str]) -> None:
        try:
            if process.poll() is None:
                if os.name == "nt":
                    try:
                        subprocess.run(
                            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            check=False,
                            shell=False,
                            timeout=5,
                        )
                    except (OSError, subprocess.TimeoutExpired):
                        process.kill()
                else:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    except OSError:
                        process.kill()

                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        finally:
            if process.stdout is not None:
                process.stdout.close()
