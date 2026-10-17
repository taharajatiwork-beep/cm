import { useEffect, useState, type FormEvent } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { ApiError } from "../api";
import { useAuth } from "../auth";
import { Button, Card, ErrorMessage, LoadingState, Muted } from "../components/ui";
import { Bi, LangSwitch, useBi } from "../i18n";
import { friendlyError } from "../lib/errors";
import { loginRedirectTarget, type LoginFrom } from "../lib/navigation";
import { symbolUrl, wordmarkUrl } from "../brand/logos";

// حساب نمایشی فقط در حالت توسعه پیش‌پر می‌شود. در build تولید import.meta.env.DEV برابر false است
// و این رشته‌ها کلاً از باندل حذف می‌شوند.
const DEMO = import.meta.env.DEV
  ? { slug: "autoco", email: "ali@autoco.example", password: "password" }
  : { slug: "", email: "", password: "" };

const SLUG_KEY = "cm.company_slug";

export function LoginPage() {
  const { user, loading, login } = useAuth();
  const location = useLocation();
  const bi = useBi();
  const [slug, setSlug] = useState(() => {
    try {
      return localStorage.getItem(SLUG_KEY) || DEMO.slug;
    } catch {
      return DEMO.slug;
    }
  });
  const [rememberSlug, setRememberSlug] = useState(() => {
    try {
      return Boolean(localStorage.getItem(SLUG_KEY));
    } catch {
      return false;
    }
  });
  const [email, setEmail] = useState(DEMO.email);
  const [password, setPassword] = useState(DEMO.password);
  const [totp, setTotp] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (loading) return <LoadingState />;
  // بعد از ورود (یا اگر از قبل لاگین بودیم) به صفحه‌ای که از آن آمدیم برمی‌گردیم، نه همیشه خانه
  if (user) {
    const from = (location.state as { from?: LoginFrom } | null)?.from;
    return <Navigate to={loginRedirectTarget(from)} replace />;
  }

  useEffect(() => {
    try {
      if (rememberSlug && slug.trim()) localStorage.setItem(SLUG_KEY, slug.trim());
      else localStorage.removeItem(SLUG_KEY);
    } catch {
      /* ignore */
    }
  }, [rememberSlug, slug]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await login(slug, email, password, totp || undefined);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? (() => {
              const f = friendlyError(err.detail);
              return bi(f.en, f.fa);
            })()
          : bi("Login failed", "ورود ناموفق"),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-page">
      <Card as="form" className="login-card" onSubmit={onSubmit}>
        <div className="login-lang">
          <LangSwitch />
        </div>
        <div className="login-brand">
          <img className="login-symbol" src={symbolUrl} alt="" width={8268} height={5874} />
          <img
            className="login-wordmark"
            src={wordmarkUrl}
            alt={bi("Sotoodeh Automotive Group", "گروه خودرویی ستوده")}
            width={8268}
            height={5874}
          />
        </div>
        <h1>
          <Bi en="Operations" fa="سامانه عملیاتی" />
        </h1>
        <p className="sub">
          <Bi en="Sign in to your branch workspace" fa="ورود به فضای کاری شعبه" />
        </p>
        {import.meta.env.DEV ? (
          <Muted as="div" className="login-demo-hint">
            <Bi en="Password for every account: password" fa="رمز همه: password" />
            <ul>
              <li><span dir="ltr">admin@</span> — <Bi en="Site admin" fa="ادمین سایت" /></li>
              <li><span dir="ltr">ali@</span> — <Bi en="Manager" fa="مدیر" /></li>
              <li><span dir="ltr">mina@</span> — <Bi en="Marketing lead" fa="سرپرست مارکتینگ" /></li>
              <li><span dir="ltr">nadia@</span> — <Bi en="Performance marketing" fa="پرفورمنس مارکتینگ" /></li>
              <li><span dir="ltr">finance@</span> — <Bi en="Lead" fa="سرپرست" /></li>
              <li><span dir="ltr">reza@</span> · <span dir="ltr">sara@</span> · <span dir="ltr">leila@</span> · <span dir="ltr">kamran@</span> · <span dir="ltr">nima@</span> — <Bi en="Member" fa="عضو" /></li>
              <li><span dir="ltr">reporter@</span> — <Bi en="Reporter" fa="گزارش‌گیر" /></li>
              <li><span dir="ltr">viewer@</span> — <Bi en="Viewer" fa="بازدیدکننده" /></li>
            </ul>
          </Muted>
        ) : null}
        <div className="field mt-4">
          <label htmlFor="login-slug">
            <Bi en="Company code" fa="کد شرکت" />
          </label>
          <input id="login-slug" value={slug} onChange={(e) => setSlug(e.target.value)} autoComplete="organization" required />
          <label className="checkbox-row">
            <input type="checkbox" checked={rememberSlug} onChange={(e) => setRememberSlug(e.target.checked)} />
            <Bi en="Remember company code" fa="یادآوری کد شرکت" />
          </label>
        </div>
        <div className="field">
          <label htmlFor="login-email">
            <Bi en="Email" fa="ایمیل" />
          </label>
          <input id="login-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" required />
        </div>
        <div className="field">
          <label htmlFor="login-password">
            <Bi en="Password" fa="رمز عبور" />
          </label>
          <input
            id="login-password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </div>
        <details className="perf-fold">
          <summary><Bi en="Two-factor code" fa="رمز دو مرحله‌ای" /></summary>
          <div className="field">
            <label htmlFor="login-totp">
              <Bi en="Authenticator code" fa="کد اپلیکیشن" />
            </label>
            <input
              id="login-totp"
              value={totp}
              onChange={(e) => setTotp(e.target.value)}
              inputMode="numeric"
              autoComplete="one-time-code"
            />
          </div>
        </details>
        <ErrorMessage message={error} friendly={false} />
        <Button type="submit" disabled={busy}>
          {busy ? bi("Signing in…", "در حال ورود…") : bi("Sign in", "ورود")}
        </Button>
      </Card>
    </div>
  );
}
