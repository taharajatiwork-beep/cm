import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import {
  Avatar,
  Button,
  Card,
  ErrorMessage,
  Icon,
  Input,
  LoadingState,
  Muted,
  PageHeader,
  SectionHeader,
} from "../components/ui";
import { Bi, useBi } from "../i18n";
import { StatusLabel } from "../ux";

type Person = Record<string, unknown>;

export function PeoplePage() {
  const bi = useBi();
  const [rows, setRows] = useState<Person[]>([]);
  const [selected, setSelected] = useState<Person | null>(null);
  const [workload, setWorkload] = useState<Awaited<ReturnType<typeof api.people.workload>> | null>(
    null,
  );
  const [reports, setReports] = useState<Person[]>([]);
  const [q, setQ] = useState("");
  const [error, setError] = useState("");
  const [loadingPerson, setLoadingPerson] = useState(false);

  useEffect(() => {
    void api.people
      .list()
      .then((list) => {
        setRows(list);
        if (list[0]) void openPerson(list[0]);
      })
      .catch((e) => setError(String((e as Error).message)));
  }, []);

  async function openPerson(p: Person) {
    setSelected(p);
    setLoadingPerson(true);
    const id = String(p.id);
    try {
      setWorkload(await api.people.workload(id));
      try {
        setReports(await api.people.reports(id));
      } catch {
        setReports([]);
      }
    } finally {
      setLoadingPerson(false);
    }
  }

  async function search(e: FormEvent) {
    e.preventDefault();
    setRows(await api.people.list(q || undefined));
  }

  return (
    <>
      <PageHeader
        title={<Bi en="Colleagues" fa="همکاران" />}
        description={
          <Bi
            en="Pick a colleague on the list to see what they are working on, or send them a message."
            fa="یک همکار را از فهرست انتخاب کنید تا ببینید روی چه کاری است، یا به او پیام بدهید."
          />
        }
      />
      <ErrorMessage error={error} />

      <div className="split split--left">
        <Card padded={false} className="side-stack" style={{ gap: 0 }}>
          <form className="card-bar" onSubmit={search}>
            <div className="search-field" style={{ maxWidth: "none" }}>
              <Icon name="search" size={14} />
              <Input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder={bi("Name or email…", "نام یا ایمیل…")}
              />
            </div>
          </form>
          {rows.length === 0 ? (
            <div className="pane-empty">
              <Bi en="No people found." fa="فردی یافت نشد." />
            </div>
          ) : (
            <ul className="rows" style={{ maxHeight: "calc(100vh - 14rem)", overflowY: "auto" }}>
              {rows.map((p) => (
                <li key={String(p.id)}>
                  <button
                    type="button"
                    className={`row-item row-button${selected?.id === p.id ? " is-active" : ""}`}
                    onClick={() => void openPerson(p)}
                  >
                    <Avatar name={String(p.full_name)} size={30} />
                    <span className="row-main">
                      <span className="row-title">{String(p.full_name)}</span>
                      <span className="row-meta">{String(p.email)}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card>
          {!selected ? (
            <div className="pane-empty">
              <Bi en="Select a person." fa="یک نفر را انتخاب کنید." />
            </div>
          ) : (
            <>
              <div className="person-head">
                <Avatar name={String(selected.full_name)} size={46} />
                <div style={{ flex: 1 }}>
                  <h2>{String(selected.full_name)}</h2>
                  <Muted className="mono">{String(selected.email)}</Muted>
                </div>
                <Button variant="secondary" to="/communication">
                  <Icon name="message" size={14} />
                  <Bi en="Message" fa="پیام" />
                </Button>
              </div>

              {loadingPerson && !workload ? (
                <LoadingState />
              ) : (
                <>
                  {workload && (
                    <div className="mini-stats">
                      <div className="mini-stat">
                        <span>
                          <Bi en="To do" fa="کار مانده" />
                        </span>
                        <strong>{workload.open_tasks}</strong>
                      </div>
                      <div className={`mini-stat${workload.overdue_tasks ? " is-danger" : ""}`}>
                        <span>
                          <Bi en="Late" fa="دیر شده" />
                        </span>
                        <strong>{workload.overdue_tasks}</strong>
                      </div>
                      <div className="mini-stat">
                        <span>
                          <Bi en="Projects" fa="پروژه‌ها" />
                        </span>
                        <strong>{workload.active_work_items}</strong>
                      </div>
                    </div>
                  )}

                  <div className="grid grid-2">
                    <div>
                      <SectionHeader
                        icon="check"
                        title={<Bi en="Working on" fa="در حال انجام" />}
                        count={workload?.tasks.length ?? 0}
                      />
                      {workload && workload.tasks.length > 0 ? (
                        <ul className="rows" style={{ border: "1px solid var(--line)", borderRadius: "var(--radius-sm)" }}>
                          {workload.tasks.map((t) => (
                            <li key={String(t.id)} className="row-item">
                              <div className="row-main">
                                <span className="row-title">{String(t.title)}</span>
                                <span className="row-meta">
                                  <StatusLabel status={String(t.status)} />
                                </span>
                              </div>
                              {t.work_item_id ? (
                                <Link
                                  to={`/work-items/${String(t.work_item_id)}`}
                                  className="icon-btn"
                                  title={bi("Open project", "باز کردن پروژه")}
                                >
                                  <Icon name="layers" />
                                </Link>
                              ) : null}
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <Muted>
                          <Bi en="Nothing assigned right now." fa="فعلاً کاری سپرده نشده." />
                        </Muted>
                      )}
                    </div>

                    <div>
                      <SectionHeader
                        icon="users"
                        title={<Bi en="Their team" fa="اعضای تیمش" />}
                        count={reports.length}
                      />
                      {reports.length > 0 ? (
                        <ul className="tag-list">
                          {reports.map((r) => (
                            <li key={String(r.id)}>
                              <Avatar name={String(r.full_name)} size={22} />
                              {String(r.full_name)}
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <Muted>
                          <Bi en="Nobody reports to them." fa="کسی زیر نظرش نیست." />
                        </Muted>
                      )}
                    </div>
                  </div>
                </>
              )}
            </>
          )}
        </Card>
      </div>
    </>
  );
}
