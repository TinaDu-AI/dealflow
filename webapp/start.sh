#!/bin/bash
# MFV Deal Flow — auto-start script
# Runs Flask server + ngrok tunnel on boot

PROJECT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="$PROJECT/webapp/logs"
PYTHON="${XHS_PYTHON:-$PROJECT/.venv/bin/python3}"
NGROK="$HOME/Library/Application Support/ngrok/ngrok"
DOMAIN="${NGROK_DOMAIN:-your-subdomain.ngrok-free.dev}"

mkdir -p "$LOG_DIR"

# Wait for network
sleep 8

# Kill any old instances
pkill -f "webapp/server.py" 2>/dev/null
pkill -f "ngrok http" 2>/dev/null
sleep 2

# Start Flask server
cd "$PROJECT"
"$PYTHON" webapp/server.py >> "$LOG_DIR/flask.log" 2>&1 &
FLASK_PID=$!
echo "Flask started: $FLASK_PID"
sleep 4

# Start ngrok with fixed domain
"$NGROK" http 5173 \
  --domain="$DOMAIN" \
  --log=stdout \
  >> "$LOG_DIR/ngrok.log" 2>&1 &

echo "ngrok started, URL: https://$DOMAIN"
echo "Logs: $LOG_DIR"
