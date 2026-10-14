"""Sync Google Sheets perf env + service-account JSON to ~/CM on the server."""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
ENV_LOCAL = ROOT / ".env"
DEPLOY_ENV = ROOT / "secrets" / "server-deploy.env"
LOCAL_KEY = ROOT / "secrets" / "perf-sheets.json"

KEYS = (
    "PERF_SHEETS_SPREADSHEET_ID",
    "PERF_SHEETS_COST_TRACKING_ID",
    "PERF_SHEETS_REGISTER_CAMPAIGN_ID",
    "PERF_SHEETS_REPORTER_ID",
    "PERF_MIZITO_BASE",
    "PERF_MIZITO_TOKEN",
)

REMOTE_HOME = "/home/didar/CM"
REMOTE_KEY = f"{REMOTE_HOME}/secrets/perf-sheets.json"


def load_local() -> dict[str, str]:
    if not ENV_LOCAL.is_file():
        print(f"missing {ENV_LOCAL}", file=sys.stderr)
        sys.exit(1)
    out: dict[str, str] = {}
    for raw in ENV_LOCAL.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key in KEYS:
            out[key] = value.strip()
    if not any(out.get(k) for k in KEYS if k.startswith("PERF_SHEETS_") and k != "PERF_MIZITO_BASE"):
        print("no PERF_SHEETS_* spreadsheet ids in local .env", file=sys.stderr)
        sys.exit(1)
    out["PERF_SHEETS_CREDENTIALS_FILE"] = REMOTE_KEY
    return out


def load_server_cfg() -> dict[str, str]:
    cfg: dict[str, str] = {}
    for raw in DEPLOY_ENV.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        cfg[k.strip()] = v.strip()
    for key in ("CM_SERVER_HOST", "CM_SERVER_USER", "CM_SERVER_PASSWORD"):
        if not cfg.get(key):
            print(f"missing {key} in {DEPLOY_ENV}", file=sys.stderr)
            sys.exit(1)
    return cfg


def restart_api_script() -> str:
    return f"""
CM={REMOTE_HOME}
stop_pid() {{
  local f="$1"
  if [ -f "$f" ]; then
    local old pgid
    old=$(cat "$f" || true)
    if [ -n "${{old:-}}" ]; then
      pgid=$(ps -o pgid= -p "$old" 2>/dev/null | tr -d ' ' || true)
      if [ -n "${{pgid:-}}" ]; then
        kill -- "-$pgid" 2>/dev/null || true
        sleep 1
        kill -9 -- "-$pgid" 2>/dev/null || true
      fi
    fi
  fi
}}
export UV_INSTALL_DIR="$CM/.tools/uv"
export UV_CACHE_DIR="$CM/.cache/uv"
export PATH="$UV_INSTALL_DIR:$CM/.tools/node/bin:$PATH"
export DATABASE_URL="postgresql+asyncpg://cm:cm@127.0.0.1:5432/cm"
export REDIS_URL="redis://127.0.0.1:6379/0"
stop_pid "$CM/api.pid"
sleep 1
cd "$CM/backend"
setsid env PATH="$PATH" UV_CACHE_DIR="$UV_CACHE_DIR" DATABASE_URL="$DATABASE_URL" REDIS_URL="$REDIS_URL" \\
  uv run uvicorn app.main:app --host 0.0.0.0 --port 8001 \\
  > "$CM/api.log" 2>&1 < /dev/null &
echo $! > "$CM/api.pid"
for _ in $(seq 1 30); do
  curl -sf http://127.0.0.1:8001/health/ready >/dev/null && echo API_READY=1 && exit 0
  sleep 1
done
echo API_READY=0
tail -15 "$CM/api.log"
exit 1
"""


def main() -> None:
    patch = load_local()
    cfg = load_server_cfg()
    patch_b64 = base64.b64encode(json.dumps(patch).encode("utf-8")).decode("ascii")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        cfg["CM_SERVER_HOST"],
        username=cfg["CM_SERVER_USER"],
        password=cfg["CM_SERVER_PASSWORD"],
        timeout=60,
    )

    if LOCAL_KEY.is_file():
        sftp = client.open_sftp()
        try:
            try:
                sftp.stat(f"{REMOTE_HOME}/secrets")
            except OSError:
                client.exec_command(f"mkdir -p {REMOTE_HOME}/secrets")[1].read()
            sftp.put(str(LOCAL_KEY), REMOTE_KEY)
            print(f"uploaded {LOCAL_KEY.name} -> {REMOTE_KEY}")
        finally:
            sftp.close()
    else:
        print(f"skip upload — {LOCAL_KEY} not found locally", file=sys.stderr)

    remote = f"""
set -euo pipefail
python3 <<'PY'
import base64, json, pathlib
patch = json.loads(base64.b64decode("{patch_b64}").decode())
path = pathlib.Path("{REMOTE_HOME}/.env")
lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
out = []
seen = set()
for line in lines:
    if "=" not in line or line.strip().startswith("#"):
        out.append(line)
        continue
    key = line.split("=", 1)[0].strip()
    if key in patch:
        out.append(f"{{key}}={{patch[key]}}")
        seen.add(key)
    else:
        out.append(line)
for key, val in patch.items():
    if key not in seen:
        out.append(f"{{key}}={{val}}")
path.write_text("\\n".join(out) + "\\n", encoding="utf-8")
key_path = pathlib.Path(patch["PERF_SHEETS_CREDENTIALS_FILE"])
print("cred_exists=" + ("yes" if key_path.is_file() else "no"))
for key in sorted(patch):
    val = patch[key]
    upper = key.upper()
    if any(s in upper for s in ("SECRET", "TOKEN", "PASSWORD", "CREDENTIALS")):
        val = "***"
    print(f"{{key}}={{val}}")
PY
{restart_api_script()}
"""

    stdin, stdout, stderr = client.exec_command("bash -s")
    stdin.write(remote)
    stdin.channel.shutdown_write()
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    client.close()
    print(out)
    if err:
        print(err, file=sys.stderr)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
