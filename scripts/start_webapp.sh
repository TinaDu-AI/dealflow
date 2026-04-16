#!/bin/bash
# Webapp server launcher
# Uses venv at ~/.local/share/xhs-venv (outside iCloud-synced Desktop)
# to avoid iCloud file-lock overhead that makes Python startup slow.
#
# To recreate the external venv:
#   UV_PROJECT_ENVIRONMENT=~/.local/share/xhs-venv uv sync

EXTERNAL_VENV="$HOME/.local/share/xhs-venv"
PROJECT_VENV="/Users/duwanshu/Desktop/xiaohongshu-skills-main/.venv"

# Use external venv if available, fall back to project venv
if [ -f "$EXTERNAL_VENV/bin/python" ]; then
    PYTHON="$EXTERNAL_VENV/bin/python"
else
    PYTHON="$PROJECT_VENV/bin/python"
fi

export no_proxy="localhost,127.0.0.1"
export NO_PROXY="localhost,127.0.0.1"

cd /Users/duwanshu/Desktop/xiaohongshu-skills-main/webapp
exec "$PYTHON" server.py
