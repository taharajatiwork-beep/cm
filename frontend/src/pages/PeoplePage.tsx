import { useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
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
import { DateText } from "../components/DateText";
import { Bi, useBi } from "../i18n";
import { queryKeys } from "../lib/queryKeys";
import { StatusLabel } from "../ux";
import { Link } from "react-router-dom";

type Person = Record<string, unknown>;

export function PeoplePage() {
  const bi = useBi();
  const [q, setQ] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const listQuery = useQuery({
    queryKey: queryKeys.people(q),
    queryFn: () => api.people.list(q || undefined),
  });
  const rows = listQuery.data ?? [];
  const error = listQuery.isError ? String((listQuery.error as Error).message) : "";

  // انتخاب اولین همکار به‌صورت مشتق‌شده — پنل هیچ‌وقت خالی نمی‌ماند و effect نمی‌خواهد
  const activeId = selectedId ?? (rows[0] ? String(rows[0].id) : "");
  const selected = rows.find((p) => String(p.id) === activeId) ?? null;

  const detailQuery = useQuery({
    queryKey: queryKeys.personDetail(activeId),
    enabled: Boolean(activeId),
    queryFn: async () => {
      const id = String(activeId);
      const workload = await api.people.workload(id);
      let reports: Person[] = [];
      try {
        reports = await api.people.reports(id);
      } catch {
        reports = [];
      }
      return { workload, reports };
    },
  });
  const workload = detailQuery.data?.workload ?? null;
  const reports = detailQuery.data?.reports ?? [];

  function search(e: FormEvent) {
    e.preventDefault();
    void listQuery.refetch();
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
      <ErrorMessage error={detailQuery.isError ? String((detailQuery.error as Error).message) : ""} />

      <div className="split split--left">
        <Card padded={false} className="side-stack side-stack--flush">
          <form className="card-bar" onSubmit={search}>
            <div className="search-field">
              <Icon name="search" size={14} />
              <Input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder={bi("Name or email…", "نام یا ایمیل…")}
              />
            </div>
          </form>
          {listQuery.isLoading ? (
            <LoadingState />
          ) : rows.length === 0 ? (
            <div className="pane-empty">
              <Bi en="No people found." fa="فردی یافت نشد." />
            </div>
          ) : (
            <ul className="rows rows--scroll">
              {rows.map((p) => (
                <li key={String(p.id)}>
                  <button
                    type="button"
                    className={`row-item row-button${activeId === String(p.id) ? " is-active" : ""}`}
                    onClick={() => setSelectedId(String(p.id))}
                  >
                    <Avatar name={String(p.full_name)} size={30} />
                    <span className="row-main">
                      <span className="row-title">{String(p.full_name)}</span>
                      <span className="row-meta ltr-value">{String(p.email)}</span>
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
            <div className="stack stack--roomy">
              <div className="person-head">
                <Avatar name={String(selected.full_name)} size={46} />
                <div className="grow">
                  <h2>{String(selected.full_name)}</h2>
                  <Muted className="mono ltr-value">{String(selected.email)}</Muted>
                  <DateText value={selected.created_at} />
                </div>
                <Button variant="secondary" to="/communication">
                  <Icon name="message" size={14} />
                  <Bi en="Message" fa="پیام" />
                </Button>
              </div>

              {detailQuery.isLoading && !workload ? (
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
                        <ul className="rows rows--boxed">
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
            </div>
          )}
        </Card>
      </div>
    </>
  );
}
