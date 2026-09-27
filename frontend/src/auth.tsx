import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { api, getToken, setToken } from "./api";

export type Me = {
  id: string;
  full_name: string;
  email: string;
  organization_id: string;
  role_id: string | null;
  branch_id: string | null;
  team_id: string | null;
  permissions: string[];
  roleCode?: string;
};

type AuthState = {
  user: Me | null;
  loading: boolean;
  login: (slug: string, email: string, password: string) => Promise<void>;
  logout: () => void;
  has: (perm: string) => boolean;
  roleHint: "admin" | "manager" | "seller" | "marketing" | "viewer";
};

const AuthContext = createContext<AuthState | null>(null);

function roleHintFromPerms(perms: string[]): AuthState["roleHint"] {
  if (perms.includes("org.admin")) return "admin";
  if (perms.includes("task.delegate") || perms.includes("task.assign")) return "manager";
  if (perms.includes("inventory.write")) return "manager";
  if (perms.includes("work_item.write") && perms.includes("case.write")) return "manager";
  // sellers/marketing share similar perms — distinguish weakly
  if (perms.includes("inventory.read") && !perms.includes("work_item.write")) return "seller";
  return "viewer";
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    if (!getToken()) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      const me = await api.me();
      let roleCode: string | undefined;
      try {
        const roles = await api.roles();
        roleCode = roles.find((r) => r.id === me.role_id)?.code;
      } catch {
        /* roles may be restricted */
      }
      setUser({ ...me, roleCode });
    } catch {
      setToken(null);
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const login = useCallback(async (slug: string, email: string, password: string) => {
    const { access_token } = await api.login(slug, email, password);
    setToken(access_token);
    setLoading(true);
    await refresh();
  }, [refresh]);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      user,
      loading,
      login,
      logout,
      has: (perm) => !!user?.permissions.includes(perm) || !!user?.permissions.includes("org.admin"),
      roleHint: user
        ? user.roleCode === "seller"
          ? "seller"
          : user.roleCode === "marketing"
            ? "marketing"
            : user.roleCode === "manager"
              ? "manager"
              : user.roleCode === "admin"
                ? "admin"
                : roleHintFromPerms(user.permissions)
        : "viewer",
    }),
    [user, loading, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside provider");
  return ctx;
}
