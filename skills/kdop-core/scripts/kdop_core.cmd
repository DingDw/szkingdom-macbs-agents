@echo off
rem KDOP 通用访问客户端 CLI 包装脚本（Windows）
rem 解释器优先级：本 skill .venv -> 同目录 kdop skill 的 .venv -> ~/.kdop/.venv -> 系统 Python
rem chcp 65001 保证中文输出不乱码
chcp 65001 >nul 2>nul
setlocal
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
set "HERE=%~dp0"
set "SCRIPT=%HERE%kdop_core.py"

set "VENV_PY=%HERE%..\.venv\Scripts\python.exe"
if exist "%VENV_PY%" (
  "%VENV_PY%" "%SCRIPT%" %*
  exit /b %ERRORLEVEL%
)

set "VENV_PY=%HERE%..\..\kdop\.venv\Scripts\python.exe"
if exist "%VENV_PY%" (
  "%VENV_PY%" "%SCRIPT%" %*
  exit /b %ERRORLEVEL%
)

set "VENV_PY=%USERPROFILE%\.kdop\.venv\Scripts\python.exe"
if exist "%VENV_PY%" (
  "%VENV_PY%" "%SCRIPT%" %*
  exit /b %ERRORLEVEL%
)

where py >nul 2>nul
if %ERRORLEVEL%==0 (
  py -3 "%SCRIPT%" %*
  exit /b %ERRORLEVEL%
)

python "%SCRIPT%" %*
exit /b %ERRORLEVEL%
