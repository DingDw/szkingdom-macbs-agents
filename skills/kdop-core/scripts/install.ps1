# KDOP 通用访问客户端 安装脚本（Windows / PowerShell）
#
# 作用：
#   1. 找到 Python 3.9+（或复用已有 KDOP venv，避免重复安装 playwright）
#   2. 准备虚拟环境并安装 playwright
#   3. 检测本机 Chrome/Edge；没有就下载 playwright 内置 Chromium
#   4. 可选安装验证码 OCR 依赖（-Ocr）
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File install.ps1
#   powershell -ExecutionPolicy Bypass -File install.ps1 -Ocr

param(
    [switch]$Ocr
)

$ErrorActionPreference = 'Stop'
$skillRoot = Split-Path -Parent $PSScriptRoot
$venvDir = Join-Path $skillRoot '.venv'
$venvPy = Join-Path $venvDir 'Scripts\python.exe'
$sharedVenvs = @(
    (Join-Path (Split-Path -Parent $skillRoot) 'kdop\.venv\Scripts\python.exe'),
    (Join-Path $env:USERPROFILE '.kdop\.venv\Scripts\python.exe')
)

function Find-Python {
    $candidates = @()
    if ($env:KDOP_PYTHON) { $candidates += $env:KDOP_PYTHON }
    foreach ($shared in $sharedVenvs) { if (Test-Path $shared) { $candidates += $shared } }
    foreach ($name in @('py', 'python', 'python3')) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if (-not $cmd) { continue }
        if ($name -eq 'py') {
            try { $exe = & py -3 -c "import sys;print(sys.executable)" 2>$null } catch { $exe = $null }
            if ($exe) { $candidates += $exe }
        } else {
            $candidates += $cmd.Source
        }
    }
    foreach ($c in $candidates) {
        if (-not $c) { continue }
        try {
            $ver = & $c -c "import sys;print('%d.%d' % sys.version_info[:2])" 2>$null
            if ($ver) {
                $parts = $ver.Split('.')
                if ([int]$parts[0] -eq 3 -and [int]$parts[1] -ge 9) { return $c }
            }
        } catch { }
    }
    return $null
}

Write-Host "[1/4] 查找 Python ..." -ForegroundColor Cyan
$python = Find-Python
if (-not $python) {
    Write-Host "未找到 Python 3.9+。请先安装 Python（https://www.python.org/downloads/）并勾选 Add to PATH。" -ForegroundColor Red
    exit 1
}
Write-Host "      使用 $python" -ForegroundColor Green

Write-Host "[2/4] 准备虚拟环境 ..." -ForegroundColor Cyan
if (-not (Test-Path $venvPy)) {
    # 已有可复用的 KDOP venv 时直接软链式复用其解释器，避免再装一份 playwright
    if ($python -like '*\.venv\Scripts\python.exe' -or (Test-Path (Join-Path $skillRoot '.venv\pyvenv.cfg'))) {
        Write-Host "      复用已有虚拟环境：$python" -ForegroundColor Green
        $venvPy = $python
    } else {
        & $python -m venv $venvDir
        if ($LASTEXITCODE -ne 0) { Write-Host "创建 venv 失败" -ForegroundColor Red; exit 1 }
    }
}
if (Test-Path $venvPy) {
    & $venvPy -m pip install --upgrade pip --quiet
    & $venvPy -m pip install --quiet playwright
    if ($LASTEXITCODE -ne 0) { Write-Host "安装 playwright 失败（检查网络 / pip 源）" -ForegroundColor Red; exit 1 }
    Write-Host "      playwright 就绪" -ForegroundColor Green
    if ($Ocr) {
        Write-Host "      安装验证码 OCR 依赖（pytesseract / pillow）..." -ForegroundColor Cyan
        & $venvPy -m pip install --quiet pytesseract pillow
        Write-Host "      注意：还需单独安装 Tesseract-OCR 并加入 PATH。" -ForegroundColor Yellow
    }
}

Write-Host "[3/4] 检查浏览器 ..." -ForegroundColor Cyan
$browser = @(
    "C:\Program Files\Google\Chrome\Application\chrome.exe",
    "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "C:\Program Files\Microsoft\Edge\Application\msedge.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($browser) {
    Write-Host "      找到 $browser" -ForegroundColor Green
} else {
    Write-Host "      未找到 Chrome/Edge，下载 playwright 内置 Chromium ..." -ForegroundColor Yellow
    & $venvPy -m playwright install chromium
}

Write-Host "[4/4] 完成" -ForegroundColor Cyan
Write-Host ""
Write-Host "下一步（一次性配置你自己的 KDOP 账号）：" -ForegroundColor Yellow
Write-Host "  `"$PSScriptRoot\kdop_core.cmd`" config set --username <工号> --password <密码>"
Write-Host "  `"$PSScriptRoot\kdop_core.cmd`" login"
Write-Host ""
Write-Host "验证与试跑：" -ForegroundColor Yellow
Write-Host "  `"$PSScriptRoot\kdop_core.cmd`" whoami"
Write-Host "  `"$PSScriptRoot\kdop_core.cmd`" versions --match `"1\.7\.9`""
