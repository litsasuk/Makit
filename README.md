# Makit

Makit 是一个配置驱动的本地安全工具调用控制台，提供类似 Metasploit 的交互方式，
用于统一组织和执行 EXE、Python 脚本与 Java JAR 工具。

> 本项目仅用于已获得明确授权的安全测试。使用者需要自行确认目标授权范围，并承担
> 使用外部工具产生的全部责任。

## 主要特性

- 工具、分类、执行模式、参数和工作流全部由 `config.json` 定义；
- 新增工具时无需修改 Python 源码；
- 支持 EXE、Python、Java 三类程序的 CLI 与 GUI 执行；
- Python 和 Java 解释器可从环境变量查找，也可在配置中指定；
- 支持单 URL、TXT 目标列表、可选请求头和 Cookie；
- 支持目标校验、敏感请求头脱敏、运行日志和独立输出目录；
- CLI 工具可保留 ANSI 颜色，并支持交互输入与 Ctrl+C 子进程树终止；
- GUI 工具启动后立即返回工具选择页，可配置 UAC 提权和启动观察时间；
- 支持按顺序运行多个工具的配置化工作流；
- 核心程序仅使用 Python 标准库。

## 支持的程序类型

| 程序类型 | CLI | GUI | 命令前缀 |
| --- | --- | --- | --- |
| EXE | `executable` | `executable` + `launch_only: true` | `<exe>` |
| Python | `script` | `script` + `launch_only: true` | `<python> -u <script>` |
| Java | `jar` | `jar` + `launch_only: true` | `<java> -jar <jar>` |

一个工具必须且只能配置 `executable`、`script`、`jar` 中的一项。所有命令都以参数
数组传递给 `subprocess`，并保持 `shell=False`。

完整字段、模式约束和六种工具示例见下方[工具配置完整参考](#工具配置完整参考)。

## 环境要求

- Python 3.10 或更高版本；
- 当前示例配置主要面向 Windows 10/11；
- Git for Windows，仅在使用一键推送脚本时需要；
- Java 工具需要合适的 Java 运行环境；
- 各外部安全工具需要自行下载，并遵守其许可证。

## 关于 `tools` 目录

仓库不会上传 `tools/` 中的第三方程序、脚本、JAR、规则库或运行时文件。克隆项目后，
请自行创建 `tools` 目录并准备所需工具，然后修改 `config.json` 中的路径。

路径可使用：

- 项目相对路径，例如 `tools\\nmap\\nmap.exe`；
- 绝对路径，例如 `D:\\SecurityTools\\tool.exe`；
- `PATH` 中可解析的命令名，例如 `nmap.exe`、`python` 或 `java`。

示例配置中包含 nmap、httpx、dirsearch、URLFinder、ENScan、subfinder、nuclei、
sqlmap、Shiro Attack、afrog、xray 和 Goby 等模块定义，但这些第三方工具本身不属于
本仓库。缺少程序文件时，执行对应模块会显示明确的路径错误。

## 快速开始

克隆仓库：

```powershell
git clone <你的仓库地址>
cd makit
Copy-Item config.demo.json config.json
```

正式 `config.json` 包含本机工具路径，不上传到仓库。克隆后先从公开 Demo 创建本地
配置，再根据本机环境修改并准备外部工具。首先检查控制台和模块配置：

```powershell
python -B main.py tools
```

启动交互控制台：

```powershell
python main.py
```

基本操作示例：

```text
makit > recon
makit (recon) > 1
makit (recon/nmap) > example.test
makit (recon/nmap) > set mode quick
makit (recon/nmap) > show
makit (recon/nmap) > run
```

裸域名默认补全为 `https://`；80、8000、8080、8888 端口默认补全为 `http://`。
TXT 文件使用 UTF-8 编码，每行一个域名或 URL，空行与 `#` 注释会被忽略，重复目标
会自动去重。

## 常用命令

| 命令 | 说明 |
| --- | --- |
| `show modes` | 显示操作模式；选中模块后显示该模块的功能模式 |
| `show tools` | 显示当前操作模式中的工具 |
| `use <编号或名称>` | 选择操作模式或工具 |
| `show` | 显示当前 URL、MODE 和 HEADERS |
| `<域名或 URL>` | 直接设置当前目标 |
| `set url <URL或TXT>` | 设置单目标或 UTF-8 TXT 列表 |
| `set mode <编号或名称>` | 切换工具功能模式 |
| `set header "Name: Value"` | 添加或替换 HTTP 请求头 |
| `set cookie "a=b"` | 设置 Cookie 请求头 |
| `unset header <名称/all>` | 删除一个或全部请求头 |
| `run` | 执行当前工具或工作流 |
| `b` / `back` | 返回上一级 |
| `q` / `exit` / `quit` | 退出 Makit |

## 非交互执行

```powershell
python main.py run nmap --target https://example.test --mode quick
python main.py run nuclei --target targets.txt --mode standard
python main.py run xray --target https://example.test --mode direct
python main.py run goby
python main.py run shiro_attack
python main.py workflow basic-web --target https://example.test --mode standard
```

GUI 工具通常不需要 `--target`。启动成功后，Makit 会立即结束本次 `run`，图形程序
继续独立运行。

## 打包为 Windows EXE

`build.cmd` 和 `build_support/` 是本地维护文件，不上传到仓库；以下流程适用于持有
完整本地项目的维护者。

源码版本和打包版本可以同时保留。打包前只需安装一次 PyInstaller：

```powershell
py -m pip install pyinstaller
```

如果 PyInstaller 提示存在不兼容的旧版 `typing` 包，可执行
`py -m pip uninstall typing`；Python 3.10 及以上已经内置 `typing`，不需要该回移植包。

然后在项目根目录运行：

```powershell
.\build.cmd
```

脚本会先校验所有 Python 源文件、正式配置和 Demo 配置，再生成单文件控制台程序，
并把 `config.demo.json` 复制为发布目录中可编辑的 `config.json`。正式配置、源码及
第三方工具不会被删除或移动。脚本只会清理经过校验的项目 `release/` 目录，最终
目录严格保留以下三个文件：

```text
release/
├─ Makit.exe
├─ config.json
└─ README.md
```

`build/` 只保存 PyInstaller 的中间文件，`release/` 保存可分发文件；两者均不会由
一键推送脚本上传。再次执行 `build.cmd` 会更新同名发布文件。

打包版始终从 `Makit.exe` 所在目录读取 `config.json`，运行任务时才按配置创建
`output/`。打包脚本不复制或创建 `tools/` 和 `output/`。
发布版配置是一个不包含本机绝对路径的 Demo，展示 EXE、Python、Java 的 CLI/GUI
配置和工作流；使用时应把示例程序路径与参数替换为实际工具的绝对路径，或者自行
在发布目录旁准备所需工具目录。
Python 脚本工具仍需使用 `PATH` 或 `python_executable` 指定的 Python，Java 工具仍需
使用 `PATH`、`JAVA_HOME` 或 `java_executable` 指定的 Java。打包 Makit 本身不会把
这些第三方解释器或工具嵌入 EXE。

## 工具配置完整参考

Makit 不按工具名称编写专用执行代码。只要在 `config.json` 的 `tools` 对象中新增一项，
即可注册工具；保存配置并重新启动后，工具会自动出现在对应 `console_mode` 的列表中。

### 通用字段

| 字段 | 说明 |
| --- | --- |
| `module` | 控制台显示及选择名称，不能与其他模块重复 |
| `console_mode` | 所属顶层操作模式，必须存在于 `console_modes` |
| `description` | 工具列表说明 |
| `enabled` | 可选；设为 `false` 时不注册 |
| `executable` | EXE 的绝对路径、项目相对路径或 `PATH` 命令名 |
| `script` | `.py` 文件路径 |
| `python_executable` | 可选；Python 绝对路径、项目相对路径或 `PATH` 命令名 |
| `jar` | `.jar` 文件路径 |
| `java_executable` | 可选；Java 绝对路径、项目相对路径或 `PATH` 命令名 |
| `required_files` | 附加规则、字典、配置等必需文件 |
| `working_directory` | 可选运行目录；支持绝对路径、项目相对路径和环境变量 |
| `encoding` | CLI 管道输出编码，默认 `utf-8` |
| `interactive` | CLI 是否继承 stdin，默认 `true`；设为 `false` 时使用 DEVNULL |
| `preserve_color` | 通过颜色环境变量要求管道工具保留 ANSI |
| `native_terminal` | CLI 直接继承 stdout/stderr，供只在 TTY 下着色的工具使用 |
| `launch_only` | `true` 表示 GUI 启动型工具，不要求 URL |
| `run_as_admin` | GUI 是否通过 Windows UAC 启动 |
| `startup_timeout` | GUI 启动观察秒数，范围 0–30，默认 2 |
| `header_args` | 每个请求头追加的参数模板，必须包含 `{header}` |
| `cookie_args` | 仅 Cookie 值参数模板，必须包含 `{cookie}` |
| `default_mode` | 兼容字段；也可在模式内使用 `default: true` |
| `modes` | 任意数量、任意合法 ID 的功能模式 |

Python 未指定解释器时先查找 `PATH` 中的 `python`，再使用启动 Makit 的 Python。
Java 未指定解释器时先查找 `PATH` 中的 `java`，再查找
`JAVA_HOME/bin/java(.exe)`。

所有 CLI 工具默认继承当前终端输入，是否真正发生交互由工具自身是否读取 stdin
决定。工具不需要输入时会正常运行；只有需要强制禁止工具等待输入时，才配置
`"interactive": false`。

### 最小配置

下面是一个 EXE CLI 示例：

```json
"mytool": {
  "module": "mytool",
  "console_mode": "scan",
  "description": "自定义安全检查",
  "executable": "tools\\mytool\\mytool.exe",
  "modes": {
    "check": {
      "name": "检查",
      "description": "检查单个目标",
      "default": true,
      "args": ["--url", "{target}", "--output", "{output_dir}\\result.json"]
    }
  }
}
```

常用占位符：

| 占位符 | 说明 |
| --- | --- |
| `{target}` | 校验并规范化后的完整 URL |
| `{host}` | 从 URL 提取的主机名 |
| `{output_dir}` | 本次任务的独立输出目录 |
| `{target_file}` | 校验和去重后的 URL 列表文件 |
| `{host_file}` | 从列表提取的主机名文件 |
| `{header}` | 完整 HTTP 请求头，仅用于 `header_args` |
| `{cookie}` | Cookie 值，仅用于 `cookie_args` |

模式 ID 和名称可自由设置，不要求使用 `standard`、`quick` 或 `full`。模式内设置
`"default": true` 可将其设为默认模式；无需目标的 CLI 模式可设置
`"requires_target": false`。

### 模式字段

```json
"modes": {
  "check": {
    "name": "检查",
    "description": "执行默认检查",
    "default": true,
    "requires_target": true,
    "args": ["--url", "{target}", "--output", "{output_dir}\\result.json"],
    "list_args": ["--list", "{target_file}", "--output", "{output_dir}\\result.json"]
  }
}
```

- 模式 ID、显示名称、说明和排列顺序完全由配置决定；
- 同一工具最多一个模式可设置 `default: true`；
- `requires_target` 对 CLI 默认是 `true`；设为 `false` 后 `args` 可以为空，且只能
  使用 `{output_dir}` 占位符；
- `list_args` 只适用于需要目标的 CLI 模式；
- GUI 模式的 `requires_target` 固定为 `false`，`args` 可为空或包含静态启动参数，
  不接受目标或输出占位符。

### 六种完整配置示例

#### EXE CLI

```json
"exe_cli": {
  "module": "exe_cli",
  "console_mode": "gadget",
  "description": "EXE 命令行工具",
  "executable": "tools\\exe-cli\\tool.exe",
  "modes": {
    "run": {
      "name": "运行",
      "description": "无需目标直接运行",
      "default": true,
      "requires_target": false,
      "args": ["--version"]
    }
  }
}
```

#### EXE GUI

```json
"exe_gui": {
  "module": "exe_gui",
  "console_mode": "gadget",
  "description": "EXE 图形工具",
  "executable": "tools\\exe-gui\\Tool.exe",
  "launch_only": true,
  "run_as_admin": false,
  "modes": {
    "open": {
      "name": "打开",
      "description": "打开图形界面",
      "default": true,
      "args": ["--profile", "default"]
    }
  }
}
```

#### Python CLI

```json
"python_cli": {
  "module": "python_cli",
  "console_mode": "gadget",
  "description": "Python 命令行工具",
  "script": "tools\\python-cli\\tool.py",
  "python_executable": "C:\\Python312\\python.exe",
  "modes": {
    "check": {
      "name": "检查",
      "description": "检查目标",
      "default": true,
      "args": ["--url", "{target}"]
    }
  }
}
```

`python_executable` 可以省略，也可以填写 `python` 或具体解释器路径。配置的 `args`
中不需要重复加入解释器、`-u` 或脚本路径。

#### Python GUI

```json
"python_gui": {
  "module": "python_gui",
  "console_mode": "gadget",
  "description": "Python 图形工具",
  "script": "tools\\python-gui\\app.py",
  "python_executable": "python",
  "launch_only": true,
  "modes": {
    "open": {
      "name": "打开",
      "description": "打开 Python GUI",
      "default": true,
      "args": []
    }
  }
}
```

#### Java CLI

```json
"java_cli": {
  "module": "java_cli",
  "console_mode": "gadget",
  "description": "Java 命令行工具",
  "jar": "tools\\java-cli\\tool.jar",
  "java_executable": "java",
  "modes": {
    "check": {
      "name": "检查",
      "description": "检查目标",
      "default": true,
      "args": ["--url", "{target}"]
    }
  }
}
```

#### Java GUI

```json
"java_gui": {
  "module": "java_gui",
  "console_mode": "gadget",
  "description": "Java 图形工具",
  "jar": "tools\\java-gui\\tool.jar",
  "java_executable": "C:\\Program Files\\Java\\bin\\java.exe",
  "launch_only": true,
  "modes": {
    "open": {
      "name": "打开",
      "description": "打开 Java GUI",
      "default": true,
      "args": []
    }
  }
}
```

`java_executable` 可以省略，也可以填写 `java` 或具体解释器路径。配置的 `args` 中
不需要重复加入 `-jar` 或 JAR 路径。

## 工作流

工作流同样由 `config.json` 定义：

```json
"basic-web": {
  "module": "basic-web",
  "console_mode": "workflow",
  "description": "基础 Web 检查流程",
  "modes": {
    "standard": {
      "name": "标准",
      "description": "依次执行多个工具",
      "default": true,
      "steps": [
        {"tool": "nmap", "mode": "standard"},
        {"tool": "httpx", "mode": "standard"}
      ]
    }
  }
}
```

普通工具失败时，工作流会记录失败并继续后续步骤；用户按 Ctrl+C 中止后会停止整个
工作流。

## 输出与安全处理

每次 CLI 执行会在 `output/` 下建立独立目录，保存：

- `commands.txt`：脱敏后的命令记录；
- `<tool>.log`：工具标准输出；
- 工具自身生成的 HTML、JSON 或其他结果文件。

Cookie、Authorization 等请求头值不会显示在选项表、控制台命令或命令日志中。
正式 `config.json`、本地维护脚本、`output/`、目标列表、Agent 内部文档和 `tools/`
由维护者本机的 `.gitignore` 排除；该忽略文件本身也不上传。

## 项目结构

```text
main.py                 控制台启动入口
configuration.py        JSON 配置加载
console/                CLI、交互状态、表格和颜色
tooling/                工具模型、配置校验、目标和参数处理
execution/              EXE/Python/Java 解析、CLI/GUI 执行和会话
workflow/               工作流配置与执行
config.json             本机正式配置，不上传
config.demo.json        公开的通用配置示例
build.cmd               本地打包脚本，不上传
build_support/hooks/    本地 PyInstaller hook，不上传
push.cmd                本地一键推送脚本，不上传
tools/                  本地第三方工具目录，不上传
output/                 本地运行结果目录，不上传
build/                  PyInstaller 中间文件，不上传
release/                EXE 发布目录，不上传
.gitignore              本机 Git 忽略规则，不上传
```

## 一键推送到 GitHub

`push.cmd` 只保留在维护者本机，不属于公开仓库内容。它会在提交前自动从 Git 索引移除
`.gitignore`、正式配置、维护脚本、第三方工具和运行输出，同时保留本地文件。

1. 在 GitHub 上创建一个空仓库，不要预先添加 README、License 或 `.gitignore`；
2. 双击项目根目录下的 `push.cmd`；
3. 首次运行时粘贴 GitHub 仓库的 HTTPS 或 SSH 地址；
4. 输入提交说明，脚本会执行初始化、暂存、提交和推送；
5. 后续修改后再次双击即可推送当前分支。

命令行中也可以执行：

```powershell
.\push.cmd
```

HTTPS 推送可使用 Git Credential Manager 登录，SSH 地址需要提前配置 GitHub SSH
密钥。如果远程仓库已经存在其他提交，脚本不会自动合并历史，需先手动处理远程提交。

## 第三方工具说明

Makit 只负责调用外部程序，不包含也不重新分发第三方安全工具。第三方工具的版权、
许可证、使用限制和更新方式均由其各自项目决定。
