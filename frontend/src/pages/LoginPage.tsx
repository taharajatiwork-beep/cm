import { useState, type FormEvent } from "react";
import { Navigate } from "react-router-dom";
import { ApiError } from "../api";
import { useAuth } from "../auth";
import { Button, Card, ErrorMessage, LoadingState, Muted } from "../components/ui";
import { Bi, LangSwitch, useBi } from "../i18n";
import { friendlyError } from "../lib/errors";

export function LoginPage() {
  const { user, loading, login } = useAuth();
  const bi = useBi();
  const [slug, setSlug] = useState("autoco");
  const [email, setEmail] = useState("ali@autoco.example");
  const [password, setPassword] = useState("password");
  const [totp, setTotp] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (loading) return <LoadingState />;
  if (user) return <Navigate to="/" replace />;

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
        <h1>
          <Bi en="CM Ops" fa="سامانه عملیاتی" />
        </h1>
        <p className="sub">
          <Bi en="Sign in to your branch workspace" fa="ورود به فضای کاری شعبه" />
        </p>
        <Muted className="login-demo-hint">
          <Bi
            en="Demo: ali@autoco.example / password (manager)"
            fa="دمو: ali@autoco.example / password (مدیر)"
          />
        </Muted>
        <div className="field mt-4">
          <label htmlFor="login-slug">
            <Bi en="Company code" fa="کد شرکت" />
          </label>
          <input id="login-slug" value={slug} onChange={(e) => setSlug(e.target.value)} required />
        </div>
        <div className="field">
          <label htmlFor="login-email">
            <Bi en="Email" fa="ایمیل" />
          </label>
          <input id="login-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
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
            required
          />
        </div>
        <div className="field">
          <label>
            <Bi en="Authenticator code" fa="رمز دو مرحله‌ای" />
          </label>
          <input value={totp} onChange={(e) => setTotp(e.target.value)} inputMode="numeric" />
        </div>
        <ErrorMessage message={error} friendly={false} />
        <Button type="submit" disabled={busy}>
          {busy ? bi("Signing in…", "در حال ورود…") : bi("Sign in", "ورود")}
        </Button>
      </Card>
    </div>
  );
}
