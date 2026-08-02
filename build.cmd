@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"

set "PROJECT_ROOT="
set "RELEASE_DIR="
for %%I in ("%~dp0.") do set "PROJECT_ROOT=%%~fI"
for %%I in ("%~dp0release") do set "RELEASE_DIR=%%~fI"
if not defined PROJECT_ROOT goto :unsafe_release
if not defined RELEASE_DIR goto :unsafe_release
if /i not "%RELEASE_DIR%"=="%PROJECT_ROOT%\release" goto :unsafe_release

if /i "%~1"=="--help" goto :show_help

where py >nul 2>&1
if not errorlevel 1 (
    set "BUILD_PYTHON=py"
    goto :python_ready
)
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python was not found. Install Python and try again.
    goto :failed
)
set "BUILD_PYTHON=python"

:python_ready
%BUILD_PYTHON% -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] PyInstaller is unavailable or the Python environment is incompatible.
    echo [INFO] Install it with: %BUILD_PYTHON% -m pip install pyinstaller
    echo [INFO] If PyInstaller reports an obsolete typing package, run:
    echo        %BUILD_PYTHON% -m pip uninstall typing
    goto :failed
)

if not exist "config.json" (
    echo [ERROR] Missing config.json.
    goto :failed
)
if not exist "config.demo.json" (
    echo [ERROR] Missing config.demo.json.
    goto :failed
)
if not exist "README.md" (
    echo [ERROR] Missing README.md.
    goto :failed
)
echo [INFO] Validating Python source and JSON configuration...
%BUILD_PYTHON% -B -c "import ast,json,pathlib; roots=['console','tooling','execution','workflow','build_support']; files=list(pathlib.Path('.').glob('*.py'))+[p for root in roots for p in pathlib.Path(root).rglob('*.py')]; [ast.parse(p.read_text(encoding='utf-8'),filename=str(p)) for p in files]; [json.loads(pathlib.Path(name).read_text(encoding='utf-8')) for name in ['config.json','config.demo.json']]; print('[OK] Source and JSON validation passed.')"
if errorlevel 1 goto :failed
%BUILD_PYTHON% -B main.py --config config.demo.json tools >nul
if errorlevel 1 (
    echo [ERROR] config.demo.json failed Makit configuration validation.
    goto :failed
)

if not exist "build" mkdir "build"
if errorlevel 1 goto :failed

if not exist "%RELEASE_DIR%\" goto :create_release
echo [INFO] Removing the previous validated release directory...
rmdir /s /q "%RELEASE_DIR%"
if exist "%RELEASE_DIR%\" (
    echo [ERROR] Could not clean the previous release directory.
    goto :failed
)

:create_release
mkdir "%RELEASE_DIR%"
if errorlevel 1 goto :failed

echo [INFO] Building release\Makit.exe...
%BUILD_PYTHON% -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --onefile ^
    --console ^
    --name Makit ^
    --additional-hooks-dir "build_support\hooks" ^
    --distpath "%RELEASE_DIR%" ^
    --workpath "build\pyinstaller" ^
    --specpath "build" ^
    "main.py"
if errorlevel 1 goto :failed

echo [INFO] Copying demo configuration and documentation...
copy /y "config.demo.json" "%RELEASE_DIR%\config.json" >nul
if errorlevel 1 goto :failed
copy /y "README.md" "%RELEASE_DIR%\README.md" >nul
if errorlevel 1 goto :failed

echo.
echo [OK] Package created successfully:
echo      %RELEASE_DIR%
echo [INFO] Release contains only Makit.exe, config.json, and README.md.
echo [INFO] Source files were preserved.
exit /b 0

:show_help
echo Usage: build.cmd
echo.
echo Builds a console-mode single-file Makit.exe and creates this layout:
echo   release\Makit.exe
echo   release\config.json
echo   release\README.md
echo Source files are not deleted or moved.
exit /b 0

:unsafe_release
echo [ERROR] Refusing to clean an unverified release path.
goto :failed

:failed
echo.
echo [FAILED] Packaging stopped. Source files were not deleted or moved.
exit /b 1
