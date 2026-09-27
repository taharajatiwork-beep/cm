import { useEffect, useState } from "react";
import { api } from "../api";
import {
  Badge,
  Button,
  Card,
  CardTitle,
  EmptyState,
  ErrorMessage,
  Muted,
  PageHeader,
  Table,
} from "../components/ui";
import { Bi, useBi } from "../i18n";

export function TeamsPage() {
  const bi = useBi();
  const [teams, setTeams] = useState<Array<Record<string, unknown>>>([]);
  const [depts, setDepts] = useState<Array<Record<string, unknown>>>([]);
  const [members, setMembers] = useState<Array<Record<string, unknown>>>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    void (async () => {
      try {
        setTeams(await api.teams.list());
        setDepts(await api.departments.list());
      } catch (e) {
        setError(String((e as Error).message));
      }
    })();
  }, []);

  async function openTeam(id: string) {
    setSelected(id);
    setMembers(await api.teams.members(id));
  }

  const deptName = (id: unknown) => {
    const d = depts.find((x) => String(x.id) === String(id));
    return d ? String(d.name) : "—";
  };

  return (
    <>
      <PageHeader
        title={<Bi en="Teams" fa="تیم‌ها" />}
        description={
          <Bi
            en="Departments and teams that can receive project."
            fa="دپارتمان‌ها و تیم‌هایی که پروژه می‌گیرند."
          />
        }
      />
      <ErrorMessage error={error} />
      <div className="grid grid-2">
        <Card>
          <CardTitle>
            <Bi en="Departments" fa="دپارتمان‌ها" />
          </CardTitle>
          <ul>
            {depts.map((d) => (
              <li key={String(d.id)}>
                {String(d.name)} <Badge>{String(d.code)}</Badge>
              </li>
            ))}
          </ul>
          <CardTitle>
            <Bi en="Teams" fa="تیم‌ها" />
          </CardTitle>
          <Table
            columns={[
              {
                key: "name",
                header: <Bi en="Name" fa="نام" />,
                render: (t) => String(t.name),
              },
              {
                key: "dept",
                header: <Bi en="Department" fa="دپارتمان" />,
                render: (t) => deptName(t.department_id),
              },
              {
                key: "actions",
                header: "",
                render: (t) => (
                  <Button
                    variant="secondary"
                    type="button"
                    onClick={() => void openTeam(String(t.id))}
                  >
                    <Bi en="Members" fa="اعضا" />
                  </Button>
                ),
              },
            ]}
            rows={teams}
            rowKey={(t) => String(t.id)}
            empty={
              <EmptyState
                titleEn="No teams"
                titleFa="تیمی نیست"
                bodyEn="Teams appear after organization bootstrap."
                bodyFa="تیم‌ها بعد از راه‌اندازی سازمان ظاهر می‌شوند."
              />
            }
          />
        </Card>
        <Card>
          <CardTitle>
            <Bi en="Members" fa="اعضا" />
          </CardTitle>
          {!selected ? (
            <Muted>
              <Bi en="Select a team." fa="یک تیم را انتخاب کنید." />
            </Muted>
          ) : members.length === 0 ? (
            <Muted>{bi("No members.", "عضوی نیست.")}</Muted>
          ) : (
            <ul>
              {members.map((m) => (
                <li key={String(m.id)}>
                  {String(m.full_name)} <Muted className="mono">{String(m.email)}</Muted>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </>
  );
}

export function BranchesPage() {
  const [rows, setRows] = useState<Array<Record<string, unknown>>>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    void api.branches
      .list()
      .then(setRows)
      .catch((e) => setError(String((e as Error).message)));
  }, []);

  return (
    <>
      <PageHeader
        title={<Bi en="Branches" fa="شعب" />}
        description={
          <Bi
            en="Physical locations that own inventory and work."
            fa="مکان‌هایی که مالک موجودی و کار هستند."
          />
        }
      />
      <ErrorMessage error={error} />
      <Card>
        <Table
          columns={[
            {
              key: "name",
              header: <Bi en="Name" fa="نام" />,
              render: (b) => String(b.name),
            },
            {
              key: "code",
              header: <Bi en="Code" fa="کد" />,
              render: (b) => <Badge>{String(b.code)}</Badge>,
            },
            {
              key: "city",
              header: <Bi en="City" fa="شهر" />,
              render: (b) => String(b.city || "—"),
            },
          ]}
          rows={rows}
          rowKey={(b) => String(b.id)}
          empty={
            <EmptyState
              titleEn="No branches"
              titleFa="شعبه‌ای نیست"
              bodyEn="Branches appear after organization bootstrap."
              bodyFa="شعب بعد از راه‌اندازی سازمان ظاهر می‌شوند."
            />
          }
        />
      </Card>
    </>
  );
}
