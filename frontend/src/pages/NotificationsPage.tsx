import { useEffect, useState } from "react";
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

export function NotificationsPage() {
  const [rows, setRows] = useState<Array<Record<string, unknown>>>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    void api
      .notifications()
      .then(setRows)
      .catch((e) => setError(String((e as Error).message)))
      .finally(() => setLoading(false));
  }, []);

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
            {rows.map((n) => (
              <ListItem key={String(n.id)}>
                <strong>{String(n.title)}</strong>
                <div>{String(n.body)}</div>
                <div>
                  <Muted>{n.created_at ? new Date(String(n.created_at)).toLocaleString() : ""}</Muted>
                </div>
              </ListItem>
            ))}
          </List>
        )}
      </Card>
    </>
  );
}
