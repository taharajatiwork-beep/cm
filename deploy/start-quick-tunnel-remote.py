"""Start trycloudflare quick tunnel on ~/CM server and set AI_LAB_CALLBACK_BASE."""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]


def server_cfg() -> dict[str, str]:
    cfg: dict[str, str] = {}
    for raw in (ROOT / "secrets/server-deploy.env").read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        cfg[k.strip()] = v.strip()
    return cfg


REMOTE = r"""
set -euo pipefail
CM=/home/didar/CM
LOG="$CM/var/cloudflared-quick.log"
PIDFILE="$CM/var/cloudflared-quick.pid"
mkdir -p "$CM/var"
if [ ! -x "$CM/.tools/cloudflared" ]; then
  curl -fsSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o "$CM/.tools/cloudflared"
  chmod +x "$CM/.tools/cloudflared"
fi
if [ -f "$PIDFILE" ]; then
  old=$(cat "$PIDFILE" || true)
  kill "$old" 2>/dev/null || true
  sleep 1
fi
: >"$LOG"
nohup "$CM/.tools/cloudflared" tunnel --url http://127.0.0.1:8001 >>"$LOG" 2>&1 &
echo $! >"$PIDFILE"
url=""
for _ in $(seq 1 60); do
  url=$(grep -oE 'https://[a-z0-9][a-z0-9-]*\.trycloudflare\.com' "$LOG" | grep -v 'api\.trycloudflare' | head -1 || true)
  [ -n "$url" ] && break
  sleep 1
done
if [ -z "$url" ]; then
  echo "NO_URL"
  tail -25 "$LOG"
  exit 1
fi
echo "TUNNEL_URL=$url"
ENV="$CM/.env"
touch "$ENV"
if grep -q '^AI_LAB_CALLBACK_BASE=' "$ENV"; then
  sed -i "s|^AI_LAB_CALLBACK_BASE=.*|AI_LAB_CALLBACK_BASE=${url}|" "$ENV"
else
  echo "AI_LAB_CALLBACK_BASE=${url}" >>"$ENV"
fi
grep '^AI_LAB_CALLBACK_BASE=' "$ENV"

stop_pid() {
  local f="$1"
  if [ -f "$f" ]; then
    local old pgid
    old=$(cat "$f" || true)
    if [ -n "${old:-}" ]; then
      pgid=$(ps -o pgid= -p "$old" 2>/dev/null | tr -d ' ' || true)
      if [ -n "${pgid:-}" ]; then
        kill -- "-$pgid" 2>/dev/null || true
        sleep 1
      fi
    fi
  fi
}
export UV_INSTALL_DIR="$CM/.tools/uv"
export UV_CACHE_DIR="$CM/.cache/uv"
export PATH="$UV_INSTALL_DIR:$CM/.tools/node/bin:$PATH"
export DATABASE_URL="postgresql+asyncpg://cm:cm@127.0.0.1:5432/cm"
export REDIS_URL="redis://127.0.0.1:6379/0"
stop_pid "$CM/api.pid"
sleep 1
cd "$CM/backend"
setsid env PATH="$PATH" UV_CACHE_DIR="$UV_CACHE_DIR" DATABASE_URL="$DATABASE_URL" REDIS_URL="$REDIS_URL" \
  uv run uvicorn app.main:app --host 0.0.0.0 --port 8001 \
  > "$CM/api.log" 2>&1 < /dev/null &
echo $! > "$CM/api.pid"
curl -sf http://127.0.0.1:8001/health/ready && echo API_READY=1
"""


def main() -> None:
    cfg = server_cfg()
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(cfg["CM_SERVER_HOST"], username=cfg["CM_SERVER_USER"], password=cfg["CM_SERVER_PASSWORD"], timeout=60)
    stdin, stdout, stderr = client.exec_command("bash -s", get_pty=False)
    stdin.write(REMOTE)
    stdin.channel.shutdown_write()
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    client.close()
    print(out)
    if err:
        print(err, file=sys.stderr)
    m = re.search(r"TUNNEL_URL=(https://[^\s]+)", out)
    if m:
        print(f"\nPublic callback base (until cloudflared restarts): {m.group(1)}")
    raise SystemExit(code)


if __name__ == "__main__":
    main()
