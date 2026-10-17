#!/bin/bash
# Quick Tunnel (trycloudflare) — بدون حساب Cloudflare، فقط برای تست AI Lab callback.
# WARNING: کل API روی :8001 از اینترنت در دسترس می‌شود؛ فقط در محیط تست.
#
# Usage on server (inside ~/CM):
#   bash deploy/cloudflared/start-quick-tunnel.sh
#
# Then set AI_LAB_CALLBACK_BASE to the printed https URL (no /api suffix) and restart API.

set -euo pipefail
CM="$(cd "$(dirname "$0")/../.." && pwd)"
LOG="$CM/var/cloudflared-quick.log"
PIDFILE="$CM/var/cloudflared-quick.pid"
API_URL="${CM_QUICK_TUNNEL_API:-http://127.0.0.1:8001}"

mkdir -p "$CM/var"
if ! command -v cloudflared >/dev/null 2>&1; then
  echo "installing cloudflared..."
  ARCH="$(uname -m)"
  case "$ARCH" in
    x86_64) BIN=cloudflared-linux-amd64 ;;
    aarch64|arm64) BIN=cloudflared-linux-arm64 ;;
    *) echo "unsupported arch: $ARCH"; exit 1 ;;
  esac
  curl -fsSL "https://github.com/cloudflare/cloudflared/releases/latest/download/${BIN}" -o /tmp/cloudflared
  chmod +x /tmp/cloudflared
  mkdir -p "$CM/.tools"
  mv /tmp/cloudflared "$CM/.tools/cloudflared"
  export PATH="$CM/.tools:$PATH"
fi
CLOUDFLARED="$(command -v cloudflared || echo "$CM/.tools/cloudflared")"

if [ -f "$PIDFILE" ]; then
  old="$(cat "$PIDFILE" || true)"
  if [ -n "${old:-}" ] && kill -0 "$old" 2>/dev/null; then
    kill "$old" 2>/dev/null || true
    sleep 1
  fi
fi

: >"$LOG"
nohup "$CLOUDFLARED" tunnel --url "$API_URL" >>"$LOG" 2>&1 &
echo $! >"$PIDFILE"

url=""
for _ in $(seq 1 45); do
  url="$(grep -oE 'https://[a-z0-9][a-z0-9-]*\.trycloudflare\.com' "$LOG" | grep -v 'api\.trycloudflare' | head -1 || true)"
  [ -n "$url" ] && break
  sleep 1
done

if [ -z "$url" ]; then
  echo "tunnel URL not found yet; see $LOG"
  tail -20 "$LOG" || true
  exit 1
fi

echo "QUICK_TUNNEL_URL=$url"
echo "Set in $CM/.env:"
echo "AI_LAB_CALLBACK_BASE=$url"
echo "Then restart API (cm-apply-update or api.pid restart)."
