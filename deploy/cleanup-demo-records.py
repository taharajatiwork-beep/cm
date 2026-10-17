#!/usr/bin/env python3
"""Remove demo business records (users, Mizito projects and tasks are kept).

Roots: all conversations/messages, customers, vehicles, cases, campaigns, work_items.
Dry run by default (lists every dependent table and row count); --apply deletes in one transaction.
Aborts if a dependent table outside ALLOWED_CHILDREN still references a root.
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

ROOTS = ["conversations", "cases", "work_items", "campaigns", "vehicles", "customers"]
ALLOWED_CHILDREN = {
    "messages", "conversation_participants",
    "vehicle_history", "vehicle_branches", "vehicle_photos", "vehicle_prices",
    "work_item_participants", "post_slots", "divar_listings",
}
NULLIFY = {("tasks", "work_item_id")}

FK_SQL = '''
    select tc.table_name, kcu.column_name, ccu.table_name as parent
    from information_schema.table_constraints tc
    join information_schema.key_column_usage kcu on tc.constraint_name = kcu.constraint_name
    join information_schema.constraint_column_usage ccu on ccu.constraint_name = tc.constraint_name
    where tc.constraint_type = 'FOREIGN KEY'
'''

async def main():
    apply = os.environ.get("APPLY") == "1"
    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with engine.begin() as conn:
        fks = (await conn.execute(text(FK_SQL))).fetchall()
        for root in ROOTS:
            n = (await conn.execute(text(f"select count(*) from {root}"))).scalar()
            print("root", root, n)
        blockers = []
        children = []
        nullify = []
        for table, column, parent in fks:
            if parent not in ROOTS or table in ROOTS and table == parent:
                continue
            n = (await conn.execute(text(f"select count(*) from {table} where {column} is not null"))).scalar()
            if n == 0:
                continue
            if (table, column) in NULLIFY:
                kind = "nullify"
            elif table in ROOTS:
                kind = "root"
            else:
                kind = "child" if table in ALLOWED_CHILDREN else "BLOCKER"
            print("ref", kind, f"{table}.{column} -> {parent}", n)
            if kind == "child":
                children.append((table, column))
            elif kind == "nullify":
                nullify.append((table, column))
            elif kind == "BLOCKER":
                blockers.append((table, column, parent, n))
        if blockers:
            print("ABORT: dependents outside allowlist", blockers)
            await conn.rollback()
            return
        if not apply:
            print("DRY_RUN (no changes)")
            await conn.rollback()
            return
        for table, column in nullify:
            res = await conn.execute(text(f"update {table} set {column} = null where {column} is not null"))
            print("unlinked", table, column, res.rowcount)
        for table, column in children:
            if table in ("messages",):
                continue
            res = await conn.execute(text(f"delete from {table} where {column} is not null"))
            print("deleted", table, res.rowcount)
        res = await conn.execute(text("update messages set reply_to_message_id = null"))
        res = await conn.execute(text("delete from messages"))
        print("deleted messages", res.rowcount)
        for root in ROOTS:
            res = await conn.execute(text(f"delete from {root}"))
            print("deleted", root, res.rowcount)
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
