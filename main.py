"""Makit 控制台及冻结版内部助手启动入口。"""

from __future__ import annotations

import sys

from console.app import main as console_main
from execution.gui import INTERNAL_LAUNCH_FLAG, main as gui_launcher_main


def main() -> int:
    """分派正常控制台与打包后复用的管理员 GUI 启动助手。"""
    if len(sys.argv) > 1 and sys.argv[1] == INTERNAL_LAUNCH_FLAG:
        return gui_launcher_main(sys.argv[2:])
    return console_main()


if __name__ == "__main__":
    raise SystemExit(main())
