#!/usr/bin/env python3
"""Delete project conversations that have no messages (auto-created by viewing a project).

Dry run by default; pass --apply to delete. One transaction; rolls back on any error.
"""

from __future__ import annotations

import sys
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
APPLY = "--apply" in sys.argv
cfg: dict[str, str] = {}
for raw in (ROOT / "secrets" / "server-deploy.env").read_text(encoding="utf-8").splitlines():
    line = raw.strip()
    if line and not line.startswith("#") and "=" in line:
        key, value = line.split("=", 1)
        cfg[key.strip()] = value.strip()

REMOTE = r"""
set -a
source /home/didar/CM/.env
set +a
cd /home/didar/CM/backend
export UV_INSTALL_DIR=/home/didar/CM/.tools/uv
export PATH="$UV_INSTALL_DIR:$PATH"
APPLY=__APPLY__ uv run python - <<'PY'
import asyncio, os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

TARGET = '''
    select c.id from conversations c
    where c.project_id is not null and c.pm_campaign_id is null
      and not exists (select 1 from messages m where m.conversation_id = c.id)
'''

async def main():
    apply = os.environ.get("APPLY") == "1"
    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with engine.begin() as conn:
        refs = (await conn.execute(text('''
            select tc.table_name, kcu.column_name from information_schema.table_constraints tc
            join information_schema.key_column_usage kcu on tc.constraint_name = kcu.constraint_name
            join information_schema.constraint_column_usage ccu on ccu.constraint_name = tc.constraint_name
            where tc.constraint_type = 'FOREIGN KEY' and ccu.table_name = 'conversations'
        '''))).fetchall()
        print("fk_refs", refs)
        targets = (await conn.execute(text(f"select count(*) from ({TARGET}) t"))).scalar()
        print("empty_project_threads", targets)
        for table, column in refs:
            if table == "conversation_participants":
                continue
            n = (await conn.execute(text(f"select count(*) from {table} where {column} in ({TARGET})"))).scalar()
            print("blocked_by", table, column, n)
        if not apply:
            print("DRY_RUN (no changes)")
            await conn.rollback()
            return
        parts = await conn.execute(text(f"delete from conversation_participants where conversation_id in ({TARGET})"))
        convs = await conn.execute(text(f"delete from conversations where id in ({TARGET})"))
        print("deleted_participants", parts.rowcount)
        print("deleted_conversations", convs.rowcount)
        left = (await conn.execute(text("select count(*) from conversations"))).scalar()
        print("conversations_left", left)
    await engine.dispose()

asyncio.run(main())
PY
""".replace("__APPLY__", "1" if APPLY else "0")

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(cfg["CM_SERVER_HOST"], username=cfg["CM_SERVER_USER"], password=cfg["CM_SERVER_PASSWORD"], timeout=60)
stdin, stdout, stderr = client.exec_command("bash -s", timeout=300)
stdin.write(REMOTE)
stdin.channel.shutdown_write()
print(stdout.read().decode("utf-8", errors="replace"))
err = stderr.read().decode("utf-8", errors="replace")
if err:
    print(err[-3000:])
raise SystemExit(stdout.channel.recv_exit_status())
