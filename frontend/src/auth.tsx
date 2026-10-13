/* Provider files intentionally export hooks beside their component — fast-refresh
   cannot hot-swap them, which is acceptable for session-wide providers. */
/* eslint-disable react/only-export-components */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { api, getToken, setToken } from "./api";
import { focusRoleFromCode, type FocusRole } from "./lib/roles";

const SESSION_HINT_KEY = "cm_session_hint";

export type Me = {
  id: string;
  full_name: string;
  email: string;
  organization_id: string;
  role_id: string | null;
  role_code?: string | null;
  role_name?: string | null;
  branch_id: string | null;
  department_id: string | null;
  team_id: string | null;
  team_home_team_id?: string | null;
  permissions: string[];
  roleCode?: string;
  branch_name?: string | null;
};

type AuthState = {
  user: Me | null;
  loading: boolean;
  login: (slug: string, email: string, password: string, totp?: string) => Promise<void>;
  logout: () => void;
  has: (perm: string) => boolean;
  /** @deprecated use focusRole — kept for gradual migration */
  roleHint: FocusRole;
  focusRole: FocusRole;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  // کوکی refresh تک‌مصرف است و سرور آن را rotate می‌کند؛ اگر دو refresh هم‌زمان
  // بروند (مثلاً double-effect در StrictMode)، دومی 401 می‌گیرد، user موقعی null
  // می‌شود و کاربرِ لاگین‌کرده به /login پرت می‌شود و مقصد اصلی‌اش را گم می‌کند.
  // زنجیره: هر اجرا بعد از اجرای قبلی و با جدیدترین توکن اجرا می‌شود.
  const chain = useRef<Promise<void>>(Promise.resolve());

  const refresh = useCallback(() => {
    const run = async () => {
      // پاسخ refresh ممکن است بعد از ورود موفق برگردد. فقط اگر نشست از زمان
      // شروع همین تلاش تغییر نکرده باشد، حق دارد state را «خارج‌شده» کند.
      const tokenAtStart = getToken();
      const hadSessionHint = localStorage.getItem(SESSION_HINT_KEY) === "1";
      if (!tokenAtStart && !hadSessionHint) {
        setUser(null);
        setLoading(false);
        return;
      }
      if (!tokenAtStart) {
        try {
          const session = await api.refresh();
          setToken(session.access_token);
        } catch {
          if (getToken() === tokenAtStart) {
            localStorage.removeItem(SESSION_HINT_KEY);
            setUser(null);
            setLoading(false);
          }
          return;
        }
      }
      try {
        const me = await api.me();
        const roleCode = me.role_code ?? undefined;
        setUser({ ...me, roleCode, branch_name: me.branch_name });
      } catch {
        setToken(null);
        setUser(null);
      } finally {
        setLoading(false);
      }
    };
    const next = chain.current.then(run);
    chain.current = next.catch(() => undefined);
    return chain.current;
  }, []);

  useEffect(() => {
    // sync session restore with the auth backend — external system, not derived state
    // eslint-disable-next-line react/set-state-in-effect
    void refresh();
  }, [refresh]);

  const login = useCallback(async (slug: string, email: string, password: string, totp?: string) => {
    const { access_token } = await api.login(slug, email, password, totp);
    setToken(access_token);
    localStorage.setItem(SESSION_HINT_KEY, "1");
    setLoading(true);
    await refresh();
  }, [refresh]);

  const logout = useCallback(() => {
    void api.logout().catch(() => undefined);
    localStorage.removeItem(SESSION_HINT_KEY);
    setToken(null);
    setUser(null);
  }, []);

  const focusRole = user ? focusRoleFromCode(user.roleCode) : "viewer";

  const value = useMemo<AuthState>(
    () => ({
      user,
      loading,
      login,
      logout,
      has: (perm) => !!user?.permissions.includes(perm) || !!user?.permissions.includes("org.admin"),
      focusRole,
      roleHint: focusRole,
    }),
    [user, loading, login, logout, focusRole],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside provider");
  return ctx;
}
