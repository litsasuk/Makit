@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"

if /i "%~1"=="--help" goto :show_help

where git >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Git was not found. Install Git for Windows and try again.
    goto :failed
)

if not exist ".git" (
    echo [INFO] Initializing Git repository...
    git init -b main >nul 2>&1
    if errorlevel 1 (
        git init
        if errorlevel 1 goto :failed
        git symbolic-ref HEAD refs/heads/main
        if errorlevel 1 goto :failed
    )
)

git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
    echo [ERROR] This directory is not a valid Git repository.
    goto :failed
)

set "ORIGIN_URL="
for /f "usebackq delims=" %%R in (`git remote get-url origin 2^>nul`) do set "ORIGIN_URL=%%R"
if defined ORIGIN_URL goto :origin_ready

echo.
echo Create an empty repository on GitHub first, then paste its HTTPS or SSH URL.
set "REMOTE_URL="
set /p "REMOTE_URL=GitHub repository URL: "
if not defined REMOTE_URL (
    echo [ERROR] Repository URL cannot be empty.
    goto :failed
)

git remote | findstr /x /c:"origin" >nul 2>&1
if errorlevel 1 goto :add_origin
git remote set-url origin "%REMOTE_URL%"
if errorlevel 1 goto :failed
goto :origin_configured

:add_origin
git remote add origin "%REMOTE_URL%"
if errorlevel 1 goto :failed

:origin_configured
set "ORIGIN_URL=%REMOTE_URL%"

:origin_ready
echo [INFO] GitHub remote: %ORIGIN_URL%

rem Remove private/local paths from the index if they were tracked previously.
git rm -r --cached --ignore-unmatch -- AGENTS.md PROJECT_CONTEXT.md tools output reports "targets*.txt" module.xray.yaml plugin.xray.yaml xray.yaml >nul 2>&1

git add -A
if errorlevel 1 goto :failed

echo.
echo [INFO] Files prepared for commit:
git status --short

git diff --cached --quiet
if errorlevel 1 goto :commit_changes

git rev-parse --verify HEAD >nul 2>&1
if errorlevel 1 (
    echo [ERROR] There are no publishable files for the first commit.
    goto :failed
)
echo [INFO] No new changes to commit. Pushing the current branch...
goto :push_changes

:commit_changes
set "COMMIT_MESSAGE="
echo [INFO] Enter a short change description below, not the GitHub repository URL.
set /p "COMMIT_MESSAGE=Commit message [Update project]: "
if not defined COMMIT_MESSAGE set "COMMIT_MESSAGE=Update project"

git commit -m "%COMMIT_MESSAGE%"
if errorlevel 1 (
    echo.
    echo [ERROR] Commit failed. Check git config user.name and user.email.
    goto :failed
)

:push_changes
set "CURRENT_BRANCH="
for /f "delims=" %%B in ('git branch --show-current') do set "CURRENT_BRANCH=%%B"
if not defined CURRENT_BRANCH (
    echo [ERROR] Could not determine the current Git branch.
    goto :failed
)

echo.
echo [INFO] Pushing branch "%CURRENT_BRANCH%" to origin...
git push -u origin "%CURRENT_BRANCH%"
if errorlevel 1 (
    echo.
    echo [ERROR] Push failed. Check authentication, remote URL, or remote commits.
    goto :failed
)

echo.
echo [OK] Project pushed successfully.
pause
exit /b 0

:show_help
echo Usage: push.cmd
echo.
echo Initializes Git when needed, commits publishable changes, and pushes the
echo current branch to the origin remote. The first run asks for a GitHub URL.
echo Files excluded by .gitignore are not uploaded.
exit /b 0

:failed
echo.
echo [FAILED] No local project files were deleted.
pause
exit /b 1
