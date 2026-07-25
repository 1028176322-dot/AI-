#!/usr/bin/env bash
# AI 创作运行平台 CLI 启动器（Linux / macOS）
# 用法：./platform.sh <cmd> [args]
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$DIR/cli/platform.py" "$@"
