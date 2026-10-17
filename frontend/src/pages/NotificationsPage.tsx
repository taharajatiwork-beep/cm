import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import {
  Button,
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
  const { has } = useAuth();
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
  const markAll = useMutation({
    mutationFn: async () => {
      const unread = (q.data ?? []).filter((n) => !n.is_read);
      await Promise.all(unread.map((n) => api.markNotificationRead(String(n.id))));
    },
    onSuccess: () => void qc.invalidateQueries({ queryKey: queryKeys.notifications }),
  });
  const rows = q.data ?? [];
  const unreadCount = rows.filter((n) => !n.is_read).length;
  const loading = q.isLoading;
  const error = q.isError ? String((q.error as Error).message) : "";

  return (
    <>
      <PageHeader
        title={<Bi en="Notifications" fa="اعلان‌ها" />}
        actions={
          unreadCount > 0 ? (
            <Button type="button" variant="secondary" disabled={markAll.isPending} onClick={() => markAll.mutate()}>
              <Bi en="Mark all read" fa="همه را خواندم" />
            </Button>
          ) : undefined
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
              const href = notificationHref(
                String(n.entity_type || ""),
                n.entity_id ? String(n.entity_id) : null,
                has,
              );
              const id = String(n.id);
              const body = (
                <>
                  <strong>{formatTitle(String(n.title))}</strong>
                  {n.body ? <div>{String(n.body)}</div> : null}
                  <Muted>
                    <DateText value={n.created_at} withTime />
                  </Muted>
                </>
              );
              if (!href) {
                return (
                  <ListItem key={id}>
                    {body}
                    {!n.is_read ? (
                      <button type="button" className="btn btn-ghost" onClick={() => mark.mutate(id)}>
                        <Bi en="Mark read" fa="خواندم" />
                      </button>
                    ) : null}
                  </ListItem>
                );
              }
              return (
                <ListItem key={id}>
                  <Link
                    className="ui-list-row-link"
                    to={href}
                    onClick={() => {
                      if (!n.is_read) mark.mutate(id);
                    }}
                  >
                    {body}
                  </Link>
                </ListItem>
              );
            })}
          </List>
        )}
      </Card>
    </>
  );
}
