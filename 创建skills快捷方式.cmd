@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem Create OpenSpec skill directory symlinks for Zed Agent.
rem Also create symlinks for every skill directory under this script's local skills folder.
rem The script is safe to rerun: existing directory symlinks/junctions are removed and recreated.
rem If a target path exists but is not a symlink/junction, the script stops and leaves it untouched.

set "OPEN_SPEC_SOURCE_ROOT=%USERPROFILE%\openspec\.codex\skills"
set "LOCAL_SOURCE_ROOT=%~dp0skills"
set "TARGET_ROOT=%USERPROFILE%\.agents\skills"

set "OPEN_SPEC_SKILLS=openspec-apply-change openspec-archive-change openspec-continue-change openspec-explore openspec-ff-change openspec-new-change openspec-propose openspec-sync-specs"

if not exist "%OPEN_SPEC_SOURCE_ROOT%\" (
    echo [ERROR] OpenSpec skills source folder does not exist: "%OPEN_SPEC_SOURCE_ROOT%"
    exit /b 1
)

if not exist "%TARGET_ROOT%\" (
    echo [INFO] Target skills folder does not exist. Creating: "%TARGET_ROOT%"
    mkdir "%TARGET_ROOT%"
    if errorlevel 1 (
        echo [ERROR] Failed to create target skills folder.
        exit /b 1
    )
)

set "HAS_ERROR=0"

echo.
echo Creating OpenSpec skill links...
for %%S in (%OPEN_SPEC_SKILLS%) do (
    call :RecreateSkillLink "%%S" "%OPEN_SPEC_SOURCE_ROOT%\%%S"
    if errorlevel 1 set "HAS_ERROR=1"
)

echo.
echo Creating local skill links...
if not exist "%LOCAL_SOURCE_ROOT%\" (
    echo [INFO] Local skills folder does not exist, skipping: "%LOCAL_SOURCE_ROOT%"
) else (
    set "LOCAL_SKILL_FOUND=0"
    for /D %%D in ("%LOCAL_SOURCE_ROOT%\*") do (
        set "LOCAL_SKILL_FOUND=1"
        call :RecreateSkillLink "%%~nxD" "%%~fD"
        if errorlevel 1 set "HAS_ERROR=1"
    )

    if "!LOCAL_SKILL_FOUND!"=="0" (
        echo [INFO] No local skill folders found under: "%LOCAL_SOURCE_ROOT%"
    )
)

if "%HAS_ERROR%"=="1" (
    echo.
    echo [ERROR] One or more skill links failed. Check the messages above.
    pause
    exit /b 1
)

echo.
echo [OK] Skill links created.
pause
exit /b 0

:RecreateSkillLink
set "SKILL_NAME=%~1"
set "SOURCE_PATH=%~2"
set "TARGET_PATH=%TARGET_ROOT%\%SKILL_NAME%"

if not exist "%SOURCE_PATH%\" (
    echo [ERROR] Source skill folder does not exist: "%SOURCE_PATH%"
    exit /b 1
)

if exist "%TARGET_PATH%" (
    fsutil reparsepoint query "%TARGET_PATH%" >nul 2>nul
    if errorlevel 1 (
        echo [ERROR] Target path already exists and is not a symlink/junction: "%TARGET_PATH%"
        exit /b 1
    )

    echo [INFO] Removing existing link: "%TARGET_PATH%"
    rmdir "%TARGET_PATH%"
    if errorlevel 1 (
        echo [ERROR] Failed to remove existing link: "%TARGET_PATH%"
        exit /b 1
    )
)

echo [LINK] "%TARGET_PATH%" -^> "%SOURCE_PATH%"
mklink /D "%TARGET_PATH%" "%SOURCE_PATH%" >nul
if errorlevel 1 (
    echo [ERROR] Failed to create link: "%TARGET_PATH%"
    exit /b 1
)

echo [OK] %SKILL_NAME%
exit /b 0
