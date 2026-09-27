import { useEffect, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import {
  Button,
  Card,
  CardTitle,
  List,
  ListItem,
  Muted,
  PageHeader,
} from "../components/ui";
import { Bi, useBi } from "../i18n";

export function DashboardPage() {
  const { user, roleHint, has } = useAuth();
  const bi = useBi();
  const [notes, setNotes] = useState<Array<Record<string, unknown>>>([]);
  const [vehicles, setVehicles] = useState<Array<Record<string, unknown>>>([]);
  const [workHits, setWorkHits] = useState<Array<Record<string, unknown>>>([]);

  useEffect(() => {
    void (async () => {
      try {
        if (has("notification.read")) setNotes(await api.notifications());
      } catch {
        /* ignore */
      }
      try {
        if (has("inventory.read")) setVehicles(await api.vehicles.list());
      } catch {
        /* ignore */
      }
      try {
        if (has("work_item.read")) {
          const items = await api.workItems.list();
          setWorkHits(
            items.slice(0, 5).map((w) => ({
              entity_type: "work_item",
              entity_id: w.id,
              title: w.title,
              status: w.status,
            })),
          );
        }
      } catch {
        /* ignore */
      }
    })();
  }, [has]);

  const title =
    roleHint === "manager" || roleHint === "admin"
      ? bi("Manager dashboard", "داشبورد مدیر")
      : roleHint === "seller"
        ? bi("Seller dashboard", "داشبورد فروشنده")
        : roleHint === "marketing"
          ? bi("Marketing dashboard", "داشبورد بازاریابی")
          : bi("Workspace", "فضای کاری");

  const blurb =
    roleHint === "manager" || roleHint === "admin"
      ? bi(
          "Track shared WorkItems, SLA pressure, and cross-team progress.",
          "پیگیری پروژه‌ها، فشار SLA و پیشرفت بین‌تیمی.",
        )
      : roleHint === "seller"
        ? bi(
            "Your customer follow-ups and vehicle-linked tasks.",
            "پیگیری مشتریان و کارهای مرتبط با خودرو.",
          )
        : roleHint === "marketing"
          ? bi(
              "Listing and campaign tasks tied to inventory.",
              "آگهی و کمپین مرتبط با موجودی.",
            )
          : bi("Limited read-only view.", "دسترسی فقط‌خواندنی محدود.");

  return (
    <>
      <PageHeader
        title={title}
        description={
          <>
            {bi("Welcome", "خوش آمدید")}, {user?.full_name}. {blurb}
          </>
        }
      />

      <div className="grid grid-3" style={{ marginBottom: "1rem" }}>
        <Card className="stat">
          <div className="label">
            <Bi en="Notifications" fa="اعلان‌ها" />
          </div>
          <div className="value">{notes.length}</div>
        </Card>
        <Card className="stat">
          <div className="label">
            <Bi en="Vehicles in view" fa="خودروهای قابل مشاهده" />
          </div>
          <div className="value">{vehicles.length}</div>
        </Card>
        <Card className="stat">
          <div className="label">
            <Bi en="Open work signals" fa="سیگنال کارهای باز" />
          </div>
          <div className="value">{workHits.length}</div>
        </Card>
      </div>

      <div className="grid grid-2">
        <Card>
          <CardTitle>
            <Bi en="Next focus" fa="تمرکز بعدی" />
          </CardTitle>
          {(roleHint === "manager" || roleHint === "admin") && (
            <ul>
              <li>
                <Button variant="ghost" to="/agent">
                  <Bi en="Ask the Communication Agent" fa="از دستیار ارتباطات بپرس" />
                </Button>{" "}
                — {bi("create multi-person WorkItems", "ساخت کار چندنفره")}
              </li>
              <li>
                <Bi en="Review" fa="بررسی" />{" "}
                <Button variant="ghost" to="/work-items">
                  <Bi en="Work Items" fa="کارها" />
                </Button>{" "}
                — {bi("progress across Reza / Marketing", "پیشرفت رضا / بازاریابی")}
              </li>
              <li>
                <Bi en="Check" fa="بررسی" />{" "}
                <Button variant="ghost" to="/vehicles">
                  <Bi en="inventory" fa="موجودی" />
                </Button>{" "}
                — {bi("aging and branch requests", "ماندگی و درخواست شعب")}
              </li>
            </ul>
          )}
          {roleHint === "seller" && (
            <ul>
              <li>
                <Bi
                  en="Complete assigned customer contact tasks"
                  fa="تکمیل تماس‌های محول‌شده با مشتری"
                />
              </li>
              <li>
                <Bi en="Open linked" fa="باز کردن" />{" "}
                <Button variant="ghost" to="/vehicles">
                  <Bi en="vehicles" fa="خودروها" />
                </Button>{" "}
                — {bi("before calling buyers", "قبل از تماس با خریدار")}
              </li>
            </ul>
          )}
          {roleHint === "marketing" && (
            <ul>
              <li>
                <Bi en="Prepare listings for assigned WorkItems" fa="آماده‌سازی آگهی برای کارهای محول‌شده" />
              </li>
              <li>
                <Bi
                  en="Confirm vehicle photos/status before publishing"
                  fa="تأیید عکس/وضعیت خودرو قبل از انتشار"
                />
              </li>
            </ul>
          )}
          {roleHint === "viewer" && (
            <Muted>
              <Bi
                en="Ask an admin for broader permissions."
                fa="برای دسترسی بیشتر از مدیر بخواهید."
              />
            </Muted>
          )}
        </Card>

        <Card>
          <CardTitle>
            <Bi en="Recent notifications" fa="اعلان‌های اخیر" />
          </CardTitle>
          {notes.length === 0 && (
            <Muted>
              <Bi en="No notifications yet." fa="هنوز اعلانی نیست." />
            </Muted>
          )}
          <List variant="timeline">
            {notes.slice(0, 6).map((n) => (
              <ListItem key={String(n.id)}>
                <strong>{String(n.title)}</strong>
                <div>
                  <Muted>{String(n.body)}</Muted>
                </div>
              </ListItem>
            ))}
          </List>
        </Card>
      </div>
    </>
  );
}
