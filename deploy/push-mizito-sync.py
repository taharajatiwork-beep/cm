#!/usr/bin/env python3
"""Upload the Mizito sync code to ~/CM, migrate, rebuild the SPA, restart API.

Does not purge data and does not write PERF_MIZITO_TOKEN.
"""

from __future__ import annotations

import sys
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / "secrets" / "server-deploy.env"
REMOTE = "/home/didar/CM"

FILES = [
    "backend/app/perf/services/mizito.py",
    "backend/app/requests/mizito_sync.py",
    "backend/app/requests/mizito_lanes.py",
    "backend/app/requests/mizito_kanban.py",
    "backend/app/requests/project_access.py",
    "backend/app/requests/models.py",
    "backend/app/requests/routes.py",
    "backend/app/requests/schemas.py",
    "backend/app/worker.py",
    "backend/app/core/config.py",
    "backend/app/core/files.py",
    "backend/app/api/routes/work.py",
    "backend/app/perf/routes.py",
    "backend/app/models/__init__.py",
    "backend/scripts/sync_mizito_work.py",
    "backend/alembic/versions/0042_work_project_mizito_lane.py",
    "backend/alembic/versions/0043_mizito_lane_boards.py",
    "backend/alembic/versions/0044_mizito_sync_state.py",
    "backend/alembic/versions/0045_calendar_v2.py",
    "backend/app/calendar/models.py",
    "backend/app/calendar/routes.py",
    "backend/app/calendar/events.py",
    "backend/app/calendar/entry_out.py",
    "backend/app/calendar/recurrence.py",
    "backend/app/calendar/occasions.py",
    "backend/app/calendar/occasions_1405.py",
    "backend/tests/test_calendar.py",
    "frontend/src/calendarApi.ts",
    "frontend/src/jalali.ts",
    "frontend/src/pages/CalendarPage.tsx",
    "frontend/src/calendar/CalendarView.tsx",
    "frontend/src/calendar/CalendarToolbar.tsx",
    "frontend/src/calendar/MonthGrid.tsx",
    "frontend/src/calendar/TimeGrid.tsx",
    "frontend/src/calendar/AgendaList.tsx",
    "frontend/src/calendar/DayDrawer.tsx",
    "frontend/src/calendar/EntryDialog.tsx",
    "frontend/src/calendar/ContentBoard.tsx",
    "frontend/src/calendar/ContentTable.tsx",
    "frontend/src/calendar/MonthHeaderCard.tsx",
    "frontend/src/calendar/WorkloadStrip.tsx",
    "frontend/src/calendar/PrintSheet.tsx",
    "frontend/src/calendar/constants.ts",
    "frontend/src/calendar/helpers.ts",
    "frontend/src/calendar/useCalendarUrlState.ts",
    "frontend/src/calendar/useCalendarUrlState.test.ts",
    "docs/project-overview.md",
    "frontend/src/requests/api.ts",
    "frontend/src/requests/ProjectsPage.tsx",
    "frontend/src/requests/projects/constants.ts",
    "frontend/src/requests/projects/useProjectsUrlState.ts",
    "frontend/src/requests/projects/ProjectsToolbar.tsx",
    "frontend/src/requests/projects/MizitoKanban.tsx",
    "frontend/src/requests/projects/KanbanColumn.tsx",
    "frontend/src/requests/projects/KanbanCard.tsx",
    "frontend/src/requests/projects/ProjectsTable.tsx",
    "frontend/src/requests/projects/ProjectQuickSheet.tsx",
    "frontend/src/styles.css",
    "frontend/src/components/ui/Icon.tsx",
    "frontend/src/requests/ProjectPage.tsx",
    "frontend/src/pages/CommunicationPage.tsx",
    "frontend/src/requests/mizitoLanes.ts",
    "frontend/src/perf/ConnectionsPage.tsx",
    "frontend/src/perf/ConnectionsPanelTile.tsx",
    "frontend/src/perf/PerfRoutes.tsx",
    "backend/app/ai_lab/access.py",
    "backend/app/ai_lab/workspaces.py",
    "backend/app/ai_lab/routes.py",
    "backend/app/ai_lab/routes_helpers.py",
    "backend/app/ai_lab/schemas.py",
    "backend/app/ai_lab/snapshots.py",
    "backend/app/ai_lab/snapshots_work.py",
    "backend/app/ai_lab/service.py",
    "backend/app/ai_lab/history.py",
    "frontend/src/ai-lab/api.ts",
    "frontend/src/pages/AiLabPage.tsx",
    "frontend/src/lib/access.ts",
    "frontend/src/api.ts",
    "frontend/src/App.tsx",
    "frontend/src/lib/focus.ts",
    "frontend/src/lib/messageMedia.ts",
    "frontend/src/lib/notificationLinks.ts",
    "frontend/src/ux.tsx",
    "frontend/src/pages/HomePage.tsx",
    "frontend/src/pages/ReportsPage.tsx",
    "frontend/src/pages/SettingsPage.tsx",
    "frontend/src/pages/settings/BrowserNotifyCard.tsx",
    "frontend/src/pages/settings/TotpCard.tsx",
    "frontend/src/requests/RequestsPage.tsx",
    "frontend/src/requests/TeamHomePage.tsx",
    "frontend/src/perf/CampaignsPage.tsx",
    "frontend/src/perf/PerfHomePage.tsx",
    "frontend/src/perf/CampaignPage.tsx",
    "frontend/src/perf/connectionsQuery.ts",
    "docs/ai-lab-setup.md",
    "docs/mizito-usage-plan.md",
    ".env.example",
]


def load_cfg() -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip()
    return out


REMOTE_SCRIPT = r"""
set -euo pipefail
CM=/home/didar/CM
export UV_INSTALL_DIR="$CM/.tools/uv"
export UV_CACHE_DIR="$CM/.cache/uv"
export PATH="$UV_INSTALL_DIR:$CM/.tools/node/bin:$PATH"
cd "$CM"
if ! grep -q '^MIZITO_SYNC_ENABLED=' .env; then
  printf '\nMIZITO_SYNC_ENABLED=true\nMIZITO_SYNC_MINUTES=15\n' >> .env
  echo SYNC_ENV=added
else
  echo SYNC_ENV=present
fi
set -a
# shellcheck disable=SC1091
source .env
set +a
cd "$CM/backend"
uv run alembic upgrade head
echo MIGRATE_OK
cd "$CM/frontend"
if [ -f package-lock.json ]; then npm run build; else npm run build; fi
echo FRONTEND_OK
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
        kill -9 -- "-$pgid" 2>/dev/null || true
      fi
    fi
  fi
}
stop_pid "$CM/api.pid"
sleep 1
cd "$CM/backend"
setsid env PATH="$PATH" UV_CACHE_DIR="$UV_CACHE_DIR" \
  uv run uvicorn app.main:app --host 0.0.0.0 --port 8001 \
  > "$CM/api.log" 2>&1 < /dev/null &
echo $! > "$CM/api.pid"
for _ in $(seq 1 40); do
  curl -sf http://127.0.0.1:8001/health/ready >/dev/null && echo API_READY=1 && exit 0
  sleep 1
done
echo API_READY=0
tail -20 "$CM/api.log"
exit 1
"""


def main() -> None:
    cfg = load_cfg()
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(cfg["CM_SERVER_HOST"], username=cfg["CM_SERVER_USER"], password=cfg["CM_SERVER_PASSWORD"], timeout=60)
    sftp = client.open_sftp()
    for rel in FILES:
        local = ROOT / rel
        remote = f"{REMOTE}/{rel.replace(chr(92), '/')}"
        remote_dir = remote.rsplit("/", 1)[0]
        client.exec_command(f"mkdir -p {remote_dir}")
        sftp.put(str(local), remote)
        print(f"put {rel}")
    sftp.close()
    stdin, stdout, stderr = client.exec_command("bash -s", timeout=600)
    stdin.write(REMOTE_SCRIPT)
    stdin.channel.shutdown_write()
    out = stdout.read().decode("utf-8", errors="replace")
    err = stderr.read().decode("utf-8", errors="replace")
    code = stdout.channel.recv_exit_status()
    client.close()
    if out:
        print(out)
    if err:
        print(err, file=sys.stderr)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
