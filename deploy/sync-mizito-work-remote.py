#!/usr/bin/env python3
"""Run Mizito → CM project sync on VPS (token from panel DB only, not .env)."""

from __future__ import annotations

import sys
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / "secrets" / "server-deploy.env"


def load_cfg() -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def main() -> None:
    purge = "--purge-manual" in sys.argv
    org = "autoco"
    for arg in sys.argv[1:]:
        if arg.startswith("--org="):
            org = arg.split("=", 1)[1]

    cfg = load_cfg()
    project = cfg.get("CM_SERVER_PROJECT_DIR", "CM")
    remote_home = f"/home/{cfg['CM_SERVER_USER']}/{project}"
    purge_flag = " --purge-manual" if purge else ""

    script = f"""
set -euo pipefail
cd {remote_home}
if docker compose -f docker-compose.prod.yml ps -q api 2>/dev/null | grep -q .; then
  docker compose -f docker-compose.prod.yml exec -T api uv run python -m scripts.sync_mizito_work --org {org}{purge_flag}
else
  cd backend
  uv run python -m scripts.sync_mizito_work --org {org}{purge_flag}
fi
"""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        cfg["CM_SERVER_HOST"],
        username=cfg["CM_SERVER_USER"],
        password=cfg["CM_SERVER_PASSWORD"],
        timeout=120,
    )
    stdin, stdout, stderr = client.exec_command("bash -s", timeout=600)
    stdin.write(script)
    stdin.channel.shutdown_write()
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    client.close()
    if out:
        print(out, end="" if out.endswith("\n") else "\n")
    if err:
        print(err, file=sys.stderr, end="" if err.endswith("\n") else "\n")
    raise SystemExit(code)


if __name__ == "__main__":
    main()
