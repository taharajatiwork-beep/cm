import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api";
import {
  Card,
  EmptyState,
  ErrorMessage,
  List,
  ListItem,
  LoadingState,
  Muted,
  PageHeader,
} from "../components/ui";
import { Bi } from "../i18n";
import { DateText } from "../components/DateText";
import { queryKeys } from "../lib/queryKeys";
import { useNotificationTitle } from "../lib/notificationTitles";
import { notificationHref } from "../lib/notificationLinks";

export function NotificationsPage() {
  const qc = useQueryClient();
  const formatTitle = useNotificationTitle();
  const q = useQuery({
    queryKey: queryKeys.notifications,
    queryFn: () => api.notifications(),
    refetchInterval: 30_000,
  });
  const mark = useMutation({
    mutationFn: (id: string) => api.markNotificationRead(id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: queryKeys.notifications }),
  });
  const rows = q.data ?? [];
  const loading = q.isLoading;
  const error = q.isError ? String((q.error as Error).message) : "";

  return (
    <>
      <PageHeader
        title={<Bi en="Notifications" fa="اعلان‌ها" />}
        description={
          <Bi
            en="Updates for you: new jobs given to you and deadlines that are close or passed."
            fa="خبرهای مربوط به شما: کارهایی که به شما سپرده شده و مهلت‌هایی که نزدیک است یا گذشته."
          />
        }
      />
      <ErrorMessage error={error} />
      <Card>
        {loading ? (
          <LoadingState />
        ) : rows.length === 0 ? (
          <EmptyState
            titleEn="No new updates"
            titleFa="خبر تازه‌ای نیست"
            bodyEn="When someone gives you a job or a deadline gets close, you’ll see it here."
            bodyFa="وقتی کسی کاری به شما بسپارد یا مهلتی نزدیک شود، اینجا می‌بینید."
          />
        ) : (
          <List variant="timeline">
            {rows.map((n) => {
              const href = notificationHref(String(n.entity_type || ""), n.entity_id ? String(n.entity_id) : null);
              return (
              <ListItem key={String(n.id)}>
                <strong>{formatTitle(String(n.title))}</strong>
                <div>{String(n.body)}</div>
                <div>
                  <Muted>
                    <DateText value={n.created_at} withTime />
                  </Muted>
                  {href ? (
                    <Link className="btn btn-ghost" to={href}>باز کردن</Link>
                  ) : null}
                  {!n.is_read ? (
                    <button type="button" className="btn btn-ghost" onClick={() => mark.mutate(String(n.id))}>
                      خواندم
                    </button>
                  ) : null}
                </div>
              </ListItem>
            );
            })}
          </List>
        )}
      </Card>
    </>
  );
}
