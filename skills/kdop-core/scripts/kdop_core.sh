#!/usr/bin/env bash
# KDOP 通用访问客户端 CLI 包装脚本（macOS / Linux）
# 解释器优先级：本 skill .venv -> 同目录 kdop skill 的 .venv -> ~/.kdop/.venv -> 系统 Python
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$HERE/kdop_core.py"

for cand in \
  "$HERE/../.venv/bin/python" \
  "$HERE/../../kdop/.venv/bin/python" \
  "$HOME/.kdop/.venv/bin/python"; do
  if [ -x "$cand" ]; then
    exec "$cand" "$SCRIPT" "$@"
  fi
done

for cand in python3 python; do
  if command -v "$cand" >/dev/null 2>&1; then
    exec "$cand" "$SCRIPT" "$@"
  fi
done
echo "未找到 Python，请先运行 scripts/install.sh" >&2
exit 1
