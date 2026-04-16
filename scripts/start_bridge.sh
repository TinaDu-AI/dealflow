#!/bin/bash
# Bridge server launcher for launchd
# Clears stale pyc files and starts bridge_server.py via system Python + venv PYTHONPATH

export PYTHONPATH="/Users/duwanshu/Desktop/xiaohongshu-skills-main/.venv/lib/python3.11/site-packages"
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
export no_proxy="localhost,127.0.0.1"
export NO_PROXY="localhost,127.0.0.1"

# Clear any stale pyc files that cause EDEADLK on rapid restart
find /Users/duwanshu/Desktop/xiaohongshu-skills-main/.venv -name "*.pyc" -delete 2>/dev/null
find /Users/duwanshu/Desktop/xiaohongshu-skills-main/scripts -name "*.pyc" -delete 2>/dev/null

cd /Users/duwanshu/Desktop/xiaohongshu-skills-main
exec /Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11 scripts/bridge_server.py
