@echo off

setlocal EnableExtensions



rem 为 Zed Agent 创建 OpenSpec skills 目录软链接。

rem 支持重复执行：已存在的同名软链接会先删除再重新创建。

rem 注意：如果同名路径不是软链接/目录联接，本脚本不会删除，避免误删真实目录。



set "SOURCE_ROOT=%USERPROFILE%\openspec\.codex\skills"

set "TARGET_ROOT=%USERPROFILE%\.agents\skills"



set "SKILLS=openspec-apply-change openspec-archive-change openspec-continue-change openspec-explore openspec-ff-change openspec-new-change openspec-propose openspec-sync-specs"



if not exist "%SOURCE_ROOT%\" (

    echo 源 skills 目录不存在: "%SOURCE_ROOT%"

    exit /b 1

)



if not exist "%TARGET_ROOT%\" (

    echo 目标 skills 目录不存在，正在创建: "%TARGET_ROOT%"

    mkdir "%TARGET_ROOT%"

    if errorlevel 1 (

        echo 创建目标 skills 目录失败。

        exit /b 1

    )

)



set "HAS_ERROR=0"



for %%S in (%SKILLS%) do (

    call :RecreateSkillLink "%%S"

    if errorlevel 1 set "HAS_ERROR=1"

)



if "%HAS_ERROR%"=="1" (

    echo.

    echo 部分 skills 软链接创建失败，请检查上方错误信息。

    pause

    exit /b 1

)



echo.

echo skills 软链接创建完成。

pause

exit /b 0



:RecreateSkillLink

set "SKILL_NAME=%~1"

set "SOURCE_PATH=%SOURCE_ROOT%\%SKILL_NAME%"

set "TARGET_PATH=%TARGET_ROOT%\%SKILL_NAME%"



if not exist "%SOURCE_PATH%\" (

    echo [失败] 源 skill 目录不存在: "%SOURCE_PATH%"

    exit /b 1

)



if exist "%TARGET_PATH%" (

    fsutil reparsepoint query "%TARGET_PATH%" >nul 2>nul

    if errorlevel 1 (

        echo [跳过] 目标路径已存在且不是软链接/目录联接: "%TARGET_PATH%"

        exit /b 1

    )



    echo [重做] 删除已有软链接: "%TARGET_PATH%"

    rmdir "%TARGET_PATH%"

    if errorlevel 1 (

        echo [失败] 删除已有软链接失败: "%TARGET_PATH%"

        exit /b 1

    )

)



echo [创建] "%TARGET_PATH%" -^> "%SOURCE_PATH%"

mklink /D "%TARGET_PATH%" "%SOURCE_PATH%" >nul

if errorlevel 1 (

    echo [失败] 创建软链接失败: "%TARGET_PATH%"

    exit /b 1

)



echo [成功] %SKILL_NAME%

exit /b 0

