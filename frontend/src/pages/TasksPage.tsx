import { useEffect, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import {
  Badge,
  Button,
  Card,
  CardTitle,
  EmptyState,
  ErrorMessage,
  PageHeader,
  Table,
} from "../components/ui";
import { Bi, useBi } from "../i18n";

export function TasksPage() {
  const { user, roleHint } = useAuth();
  const bi = useBi();
  const [mine, setMine] = useState<Array<Record<string, unknown>>>([]);
  const [overdue, setOverdue] = useState<Array<Record<string, unknown>>>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    void (async () => {
      try {
        if (user?.id) {
          setMine(await api.tasks.list({ assignee_id: user.id }));
        }
        if (roleHint === "manager" || roleHint === "admin") {
          setOverdue(await api.tasks.list({ overdue_only: true }));
        }
      } catch (e) {
        setError(String((e as Error).message));
      }
    })();
  }, [user?.id, roleHint]);

  async function complete(id: string) {
    await api.tasks.complete(id);
    if (user?.id) setMine(await api.tasks.list({ assignee_id: user.id }));
    if (roleHint === "manager" || roleHint === "admin") {
      setOverdue(await api.tasks.list({ overdue_only: true }));
    }
  }

  function taskColumns(showComplete?: boolean) {
    return [
      {
        key: "title",
        header: <Bi en="Title" fa="عنوان" />,
        render: (t: Record<string, unknown>) => String(t.title),
      },
      {
        key: "status",
        header: <Bi en="Status" fa="وضعیت" />,
        render: (t: Record<string, unknown>) => (
          <Badge tone={t.status === "COMPLETED" ? "ok" : ""}>{String(t.status)}</Badge>
        ),
      },
      {
        key: "work",
        header: <Bi en="Work item" fa="کار" />,
        render: (t: Record<string, unknown>) =>
          t.work_item_id ? (
            <Button variant="ghost" to={`/work-items/${String(t.work_item_id)}`}>
              {String(t.work_item_id).slice(0, 8)}
            </Button>
          ) : (
            "—"
          ),
      },
      {
        key: "actions",
        header: "",
        render: (t: Record<string, unknown>) =>
          showComplete && t.status !== "COMPLETED" ? (
            <Button variant="secondary" type="button" onClick={() => void complete(String(t.id))}>
              <Bi en="Complete" fa="اتمام" />
            </Button>
          ) : null,
      },
    ];
  }

  return (
    <>
      <PageHeader
        title={<Bi en="Tasks" fa="تسک‌ها" />}
        description={
          <Bi
            en="Owned actions with assignees, deadlines, and links to projects."
            fa="اقدام‌های مشخص با مسئول، مهلت، و اتصال به پروژه."
          />
        }
      />
      <ErrorMessage error={error} />
      <Card style={{ marginBottom: "1rem" }}>
        <CardTitle>
          <Bi en="My tasks" fa="تسک‌های من" />
        </CardTitle>
        <Table
          columns={taskColumns(true)}
          rows={mine}
          rowKey={(t) => String(t.id)}
          empty={
            <EmptyState
              titleEn="No open tasks"
              titleFa="تسک بازی نیست"
              bodyEn="Tasks assigned to you will appear here."
              bodyFa="وظایف محول‌شده به شما اینجا نمایش داده می‌شوند."
            />
          }
        />
      </Card>
      {(roleHint === "manager" || roleHint === "admin") && (
        <Card>
          <CardTitle>
            <Bi en="Overdue (org)" fa="معوق (سازمان)" />
          </CardTitle>
          <Table
            columns={taskColumns()}
            rows={overdue}
            rowKey={(t) => String(t.id)}
            empty={<p className="muted">{bi("Nothing overdue.", "مورد معوقی نیست.")}</p>}
          />
        </Card>
      )}
    </>
  );
}
