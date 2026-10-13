#!/usr/bin/env python3
"""Deploy CM to the internal server under ~/CM only.

Reads secrets/server-deploy.env. Uploads cm-update.tar.gz (from repo root) and
runs ~/CM/cm-apply-update.sh when present; otherwise git pull + manual restart.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / "secrets" / "server-deploy.env"
ARCHIVE = ROOT / "cm-update.tar.gz"


def load_env(path: Path) -> dict[str, str]:
    if not path.is_file():
        print(f"missing {path} — copy deploy/server.local.example", file=sys.stderr)
        sys.exit(1)
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def connect(cfg: dict[str, str]):
    import paramiko

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=cfg["CM_SERVER_HOST"],
        username=cfg["CM_SERVER_USER"],
        password=cfg["CM_SERVER_PASSWORD"],
        timeout=60,
    )
    return client


def run(client, script: str) -> int:
    stdin, stdout, stderr = client.exec_command("bash -s")
    stdin.write(script)
    stdin.channel.shutdown_write()
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    if out:
        print(out, end="" if out.endswith("\n") else "\n")
    if err:
        print(err, file=sys.stderr, end="" if err.endswith("\n") else "\n")
    return code


def main() -> None:
    probe = "--probe" in sys.argv
    cfg = load_env(ENV_FILE)
    for key in ("CM_SERVER_HOST", "CM_SERVER_USER", "CM_SERVER_PASSWORD"):
        if not cfg.get(key):
            print(f"missing {key} in {ENV_FILE}", file=sys.stderr)
            sys.exit(1)

    project = cfg.get("CM_SERVER_PROJECT_DIR", "CM")
    remote_home = f"/home/{cfg['CM_SERVER_USER']}/{project}"

    client = connect(cfg)

    if probe:
        body = f"""
set -e
cd {remote_home}
echo "PWD=$(pwd)"
test -f docker-compose.prod.yml && echo compose_prod=present || true
test -f cm-apply-update.sh && echo apply_script=present || true
git rev-parse --short HEAD 2>/dev/null || true
docker compose -f docker-compose.prod.yml ps 2>&1 | head -5 || true
pgrep -af 'uvicorn app.main' 2>/dev/null | grep {remote_home} || true
"""
        raise SystemExit(run(client, body))

    if not ARCHIVE.is_file():
        print(f"missing {ARCHIVE} — run: git archive -o cm-update.tar.gz HEAD", file=sys.stderr)
        sys.exit(1)

    remote_archive = f"{remote_home}/cm-update.tar.gz"
    print(f"uploading {ARCHIVE.name} -> {remote_archive}")
    sftp = client.open_sftp()
    sftp.put(str(ARCHIVE), remote_archive)
    sftp.close()

    body = f"""
set -e
cd {remote_home}
if [ ! -f cm-apply-update.sh ]; then
  echo "cm-apply-update.sh missing — not changing anything else"
  exit 1
fi
bash cm-apply-update.sh
"""
    code = run(client, body)
    client.close()
    raise SystemExit(code)


if __name__ == "__main__":
    main()
