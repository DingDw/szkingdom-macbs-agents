@echo off

setlocal EnableExtensions



rem 在指定目录创建当前脚本所在目录下 docs、AGENTS.md、openspec 的软链接。

rem 用法：创建AGENT资源软链接.cmd "D:\target\dir"



set "SOURCE_DIR=%~dp0"

set "TARGET_DIR=%~1"



if "%TARGET_DIR%"=="" (

    set /p "TARGET_DIR=请输入要创建软链接的目标目录: "

)



if "%TARGET_DIR%"=="" (

    echo 未指定目标目录。

    exit /b 1

)



if not exist "%TARGET_DIR%" (

    echo 目标目录不存在，正在创建: "%TARGET_DIR%"

    mkdir "%TARGET_DIR%"

    if errorlevel 1 (

        echo 创建目标目录失败。

        exit /b 1

    )

)



call :CreateDirLink "docs"

if errorlevel 1 exit /b 1



call :CreateFileLink "AGENTS.md"

if errorlevel 1 exit /b 1



call :CreateDirLink "openspec"

if errorlevel 1 exit /b 1



echo.

echo 软链接创建完成。

exit /b 0



:CreateDirLink

set "LINK_NAME=%~1"

set "LINK_PATH=%TARGET_DIR%\%LINK_NAME%"

set "SOURCE_PATH=%SOURCE_DIR%%LINK_NAME%"



if not exist "%SOURCE_PATH%\" (

    echo 源目录不存在: "%SOURCE_PATH%"

    exit /b 1

)



if exist "%LINK_PATH%" (

    echo 已存在，跳过: "%LINK_PATH%"

    exit /b 0

)



echo 创建目录软链接: "%LINK_PATH%" -^> "%SOURCE_PATH%"

mklink /D "%LINK_PATH%" "%SOURCE_PATH%"

exit /b %errorlevel%



:CreateFileLink

set "LINK_NAME=%~1"

set "LINK_PATH=%TARGET_DIR%\%LINK_NAME%"

set "SOURCE_PATH=%SOURCE_DIR%%LINK_NAME%"



if not exist "%SOURCE_PATH%" (

    echo 源文件不存在: "%SOURCE_PATH%"

    exit /b 1

)



if exist "%LINK_PATH%" (

    echo 已存在，跳过: "%LINK_PATH%"

    exit /b 0

)



echo 创建文件软链接: "%LINK_PATH%" -^> "%SOURCE_PATH%"

mklink "%LINK_PATH%" "%SOURCE_PATH%"

exit /b %errorlevel%

