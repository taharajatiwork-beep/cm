import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Badge, Button, ErrorMessage, Field, Input, Muted } from "../components/ui";
import { useToast } from "../components/ui/Toast";
import { Bi } from "../i18n";
import { perfApi, type Connections } from "./api";

type PanelRow = Connections["panels"][number];
type Tone = "ok" | "warn" | "danger" | "busy";

function panelTone(panel: PanelRow): Tone {
  if (panel.live) return panel.live.ok ? "ok" : "danger";
  return panel.ready ? "warn" : "danger";
}

export function PanelTile({
  panel,
  writable,
  checking,
  onSaved,
}: {
  panel: PanelRow;
  writable: boolean;
  checking: boolean;
  onSaved: () => void;
}) {
  const toast = useToast();
  const panelsDetail = useQuery({ queryKey: ["perf", "panels"], queryFn: perfApi.panels });
  const detail = panelsDetail.data?.find((row) => row.id === panel.id);
  const [base, setBase] = useState(panel.api_base || "");
  const [token, setToken] = useState("");
  const [username, setUsername] = useState("");
  const [secret, setSecret] = useState("");
  const [sender, setSender] = useState("");
  const [busy, setBusy] = useState(false);
  const tone = panelTone(panel);
  const canProbe = Boolean((panel.api_base || "").trim() && panel.has_token);
  useEffect(() => {
    if (!detail) return;
    setUsername(detail.api_username || "");
    setSender(detail.sender_line || "");
  }, [detail?.id, detail?.api_username, detail?.sender_line]);
  function save() {
    setBusy(true);
    const payload: Record<string, string> = {};
    if (base.trim()) payload.api_base = base.trim();
    if (token.trim()) payload.api_token = token.trim();
    perfApi
      .updatePanel(panel.id, payload)
      .then(() => {
        toast("اتصال پنل ذخیره شد؛ با «بررسی همین حالا» زنده خوانده می‌شود");
        setToken("");
        onSaved();
      })
      .catch((error: Error) => toast(error.message))
      .finally(() => setBusy(false));
  }
  function saveSmsLogin() {
    if (!detail) return;
    setBusy(true);
    const payload: Record<string, string> = { api_username: username, sender_line: sender };
    if (secret.trim()) payload.api_secret = secret.trim();
    perfApi
      .updatePanel(detail.id, payload)
      .then(() => {
        toast(secret.trim() || detail.has_secret ? "اتصال آی‌اس‌ام‌اس ذخیره شد" : "نام کاربری ذخیره شد. رمز وب‌سرویس هنوز خالی است.");
        setSecret("");
        void panelsDetail.refetch();
        onSaved();
      })
      .catch((error: Error) => toast(error.message))
      .finally(() => setBusy(false));
  }
  function saveSenderLine() {
    if (!detail) return;
    setBusy(true);
    perfApi
      .updatePanel(detail.id, { sender_line: sender })
      .then(() => {
        toast("خط ارسال ذخیره شد");
        void panelsDetail.refetch();
        onSaved();
      })
      .catch((error: Error) => toast(error.message))
      .finally(() => setBusy(false));
  }
  return (
    <article className="conn-tile" data-tone={tone}>
      <div className="conn-tile-head">
        <h3>{panel.name}</h3>
        {panel.live ? (
          panel.live.ok ? (
            <Badge tone="ok">
              <Bi en="Live OK" fa="وصل" />
            </Badge>
          ) : (
            <Badge tone="danger">
              <Bi en="Live failed" fa="باز نشد" />
            </Badge>
          )
        ) : panel.ready ? (
          <Badge tone="warn">{checking ? <Bi en="Checking" fa="در حال بررسی" /> : <Bi en="Not checked" fa="بررسی نشده" />}</Badge>
        ) : (
          <Badge tone="danger">
            <Bi en="No API login" fa="ورود API نیست" />
          </Badge>
        )}
      </div>
      {panel.live ? (
        panel.live.ok ? (
          <>
            <p className="conn-help">موجودی زنده: {panel.live.balance || "پاسخ بدون عدد"} </p>
            {panel.live.lines && panel.live.lines.length > 0 ? (
              <Muted>
                خطوط: <span dir="ltr">{panel.live.lines.join(" · ")}</span>
              </Muted>
            ) : null}
          </>
        ) : (
          <ErrorMessage friendly={false} message={panel.live.reason || "کال زنده به پنل انجام نشد."} />
        )
      ) : (
        <p className="conn-help">
          {panel.detail}
          {panel.ready && !canProbe ? " آدرس API یا کلید پنل خالی است؛ با ذخیرهٔ آن‌ها موجودی زنده خوانده می‌شود." : ""}
        </p>
      )}
      {writable ? (
        <div className="panel-probe-form">
          {panel.code === "pishgam" || panel.code === "isms" ? null : (
            <>
              <Input placeholder="آدرس API پنل (مثل https://api.example.ir)" value={base} onChange={(event) => setBase(event.target.value)} />
              <Input
                type="password"
                autoComplete="off"
                placeholder={panel.has_token ? "کلید ذخیره شده" : "کلید API"}
                value={token}
                onChange={(event) => setToken(event.target.value)}
              />
              <Button type="button" variant="secondary" disabled={busy || (!base.trim() && !token.trim())} onClick={save}>
                <Bi en="Save API" fa="ذخیره API" />
              </Button>
            </>
          )}
          {panel.code === "isms" && detail ? (
            <>
              <Field label={<Bi en="Username" fa="نام کاربری آی‌اس‌ام‌اس" />}>
                <Input value={username} onChange={(event) => setUsername(event.target.value)} />
              </Field>
              <Field label={<Bi en="API password" fa="رمز وب‌سرویس" />}>
                <Input
                  type="password"
                  autoComplete="off"
                  value={secret}
                  placeholder={detail.has_secret ? "رمز ذخیره شده" : ""}
                  onChange={(event) => setSecret(event.target.value)}
                />
              </Field>
              <Field label={<Bi en="Sender line" fa="خط ارسال" />}>
                <Input value={sender} onChange={(event) => setSender(event.target.value)} />
              </Field>
              <Button type="button" variant="secondary" disabled={busy} onClick={saveSmsLogin}>
                <Bi en="Save iSMS login" fa="ذخیرهٔ ورود آی‌اس‌ام‌اس" />
              </Button>
            </>
          ) : null}
          {panel.code === "pishgam" && detail ? (
            <>
              <Field label={<Bi en="Sender line" fa="خط ارسال" />}>
                <Input dir="ltr" value={sender} placeholder="مثل 5000302137682" onChange={(event) => setSender(event.target.value)} />
              </Field>
              <Button type="button" variant="secondary" disabled={busy} onClick={saveSenderLine}>
                <Bi en="Save sender line" fa="ذخیرهٔ خط ارسال" />
              </Button>
            </>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}
