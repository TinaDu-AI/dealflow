#!/bin/bash
# MFV Webapp startup script — used by launchd
cd "$(dirname "$0")"

VENV="/Users/duwanshu/Desktop/xiaohongshu-skills-main/.venv"
export VIRTUAL_ENV="$VENV"
export PATH="$VENV/bin:$PATH"
export PYTHONPATH=""
export PYTHONDONTWRITEBYTECODE=1

exec "$VENV/bin/python" server.py
