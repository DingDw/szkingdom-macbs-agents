#!/usr/bin/env bash
# KDOP 通用访问客户端 安装脚本（macOS / Linux）
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(dirname "$HERE")"
VENV="$SKILL_ROOT/.venv"
VENV_PY="$VENV/bin/python"

pick_python() {
  for cand in "${KDOP_PYTHON:-}" \
              "$SKILL_ROOT/../kdop/.venv/bin/python" \
              "$HOME/.kdop/.venv/bin/python" \
              python3 python; do
    [ -n "$cand" ] || continue
    if command -v "$cand" >/dev/null 2>&1 || [ -x "$cand" ]; then
      if "$cand" -c 'import sys;raise SystemExit(0 if sys.version_info[:2]>=(3,9) else 1)' 2>/dev/null; then
        echo "$cand"
        return 0
      fi
    fi
  done
  return 1
}

echo "[1/3] 查找 Python ..."
PY="$(pick_python || true)"
if [ -z "${PY}" ]; then
  echo "未找到 Python 3.9+，请先安装 Python。" >&2
  exit 1
fi
echo "      使用 $PY"

echo "[2/3] 准备虚拟环境 ..."
if [ -x "$VENV_PY" ]; then
  echo "      复用 $VENV"
elif [ -x "$SKILL_ROOT/../kdop/.venv/bin/python" ] || [ -x "$HOME/.kdop/.venv/bin/python" ]; then
  # 已有 KDOP venv 时直接复用，避免重复安装 playwright
  VENV_PY="$PY"
  echo "      复用已有虚拟环境 $PY"
else
  "$PY" -m venv "$VENV"
  VENV_PY="$VENV/bin/python"
fi
"$VENV_PY" -m pip install --upgrade pip --quiet
"$VENV_PY" -m pip install --quiet playwright

echo "[3/3] 检查浏览器 ..."
if command -v google-chrome >/dev/null 2>&1 || command -v chromium >/dev/null 2>&1 \
   || [ -x "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" ]; then
  echo "      已安装 Chrome/Chromium"
else
  echo "      下载 playwright 内置 Chromium ..."
  "$VENV_PY" -m playwright install chromium
fi

cat <<EOF

完成。下一步（一次性）：
  $HERE/kdop_core.sh config set --username <工号> --password <密码>
  $HERE/kdop_core.sh login
  $HERE/kdop_core.sh whoami
EOF
