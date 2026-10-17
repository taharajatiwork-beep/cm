import { useState } from "react";
import { Badge, Button, Muted } from "../../components/ui";
import { useToast } from "../../components/ui/Toast";
import { Bi, useBi } from "../../i18n";

export function BrowserNotifyCard() {
  const bi = useBi();
  const toast = useToast();
  const [perm, setPerm] = useState<NotificationPermission | "unsupported">(() =>
    typeof window !== "undefined" && "Notification" in window ? Notification.permission : "unsupported",
  );

  async function enable() {
    if (!("Notification" in window)) return;
    const next = await Notification.requestPermission();
    setPerm(next);
    if (next === "granted") {
      localStorage.setItem("cm-browser-notify", "1");
      toast(bi("Browser notifications enabled", "اعلان مرورگر فعال شد"));
    } else if (next === "denied") {
      toast(bi("Blocked in browser settings", "در تنظیمات مرورگر مسدود شده"));
    }
  }

  if (perm === "unsupported") {
    return (
      <Muted>
        <Bi en="This browser does not support notifications." fa="این مرورگر اعلان را پشتیبانی نمی‌کند." />
      </Muted>
    );
  }

  return (
    <div className="row">
      <Badge tone={perm === "granted" ? "ok" : perm === "denied" ? "danger" : ""}>
        {perm === "granted" ? bi("Allowed", "مجاز") : perm === "denied" ? bi("Blocked", "مسدود") : bi("Not asked", "هنوز پرسیده نشده")}
      </Badge>
      {perm !== "granted" ? (
        <Button type="button" className="btn-sm" variant="secondary" onClick={() => void enable()}>
          <Bi en="Allow in browser" fa="اجازه در مرورگر" />
        </Button>
      ) : null}
    </div>
  );
}
