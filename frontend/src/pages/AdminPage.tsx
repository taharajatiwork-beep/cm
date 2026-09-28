import { useEffect, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, getToken } from "../api";
import {
  Button,
  Card,
  EmptyState,
  ErrorMessage,
  Field,
  Input,
  LoadingState,
  Muted,
  PageHeader,
  SectionHeader,
  Select,
  Table,
} from "../components/ui";
import { Bi, useBi } from "../i18n";
import { useAuth } from "../auth";
import { useConfirm } from "../components/ui/ConfirmDialog";
import { useToast } from "../components/ui/Toast";
import { queryKeys } from "../lib/queryKeys";

const SCOPES: Array<[string, string, string]> = [
  ["organization", "Organization", "کل سازمان"],
  ["branch", "Branch", "شعبه"],
  ["department", "Department", "واحد"],
  ["team", "Team", "تیم"],
  ["self", "Self only", "فقط خودم"],
];

export function AdminPage() {
  const bi = useBi();
  const { has } = useAuth();
  const qc = useQueryClient();
  const isAdmin = has("org.admin");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const toast = useToast();
  const confirm = useConfirm();
  useEffect(() => {
    if (message) toast(message);
  }, [message, toast]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const res = await fetch("/api/org/users", {
      method: "POST",
      credentials: "include",
      headers: {
        Authorization: `Bearer ${getToken() ?? ""}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ email, full_name: name, password }),
    });
    setMessage(res.ok ? "ساخته شد" : await res.text());
  }

  const [formError, setFormError] = useState("");
  const [resetFor, setResetFor] = useState<string | null>(null);
  const [resetValue, setResetValue] = useState("");
  const [teamFor, setTeamFor] = useState<string | null>(null);
  const [teamId, setTeamId] = useState("");
  const [selectedRole, setSelectedRole] = useState("");

  const invalidateAdmin = () => {
    void qc.invalidateQueries({ queryKey: queryKeys.peopleRoot });
    void qc.invalidateQueries({ queryKey: ["admin"] });
  };

  const peopleQuery = useQuery({
    queryKey: ["admin", "people"],
    enabled: isAdmin,
    queryFn: () => api.people.list(),
  });
  const rolesQuery = useQuery({
    queryKey: ["admin", "roles"],
    enabled: isAdmin,
    queryFn: () => api.roles(),
  });
  const teamsQuery = useQuery({
    queryKey: queryKeys.teams,
    enabled: isAdmin,
    queryFn: () => api.teams.list(),
  });
  const codesQuery = useQuery({
    queryKey: ["admin", "permission-codes"],
    enabled: isAdmin,
    queryFn: () => api.admin.permissionCodes(),
  });
  const roleId = selectedRole || rolesQuery.data?.[0]?.id || "";
  const roleQuery = useQuery({
    queryKey: ["admin", "role", roleId],
    enabled: isAdmin && Boolean(roleId),
    queryFn: () => api.admin.rolePermissions(roleId),
  });

  const [userQuery, setUserQuery] = useState("");
  const people = (peopleQuery.data ?? []).filter((person) => {
    const blob = `${person.full_name || ""} ${person.email || ""}`.toLowerCase();
    return blob.includes(userQuery.trim().toLowerCase());
  });
  const roles = rolesQuery.data ?? [];
  const teams = teamsQuery.data ?? [];
  const loadError = peopleQuery.isError ? String((peopleQuery.error as Error).message) : "";

  const updateUser = useMutation({
    mutationFn: (body: { user_id: string; is_active: boolean }) =>
      api.admin.updateUser(body.user_id, { is_active: body.is_active }),
    onSuccess: () => {
      setMessage(bi("User updated", "کاربر به‌روزرسانی شد"));
      invalidateAdmin();
    },
    onError: (e) => setFormError(String((e as Error).message)),
  });

  const resetPassword = useMutation({
    mutationFn: (body: { user_id: string; password: string }) =>
      api.admin.updateUser(body.user_id, { password: body.password }),
    onSuccess: () => {
      setResetFor(null);
      setResetValue("");
      setMessage(bi("Password reset", "رمز عبور بازنشانی شد"));
      invalidateAdmin();
    },
    onError: (e) => setFormError(String((e as Error).message)),
  });

  const addTeam = useMutation({
    mutationFn: (body: { user_id: string; team_id: string }) =>
      api.admin.addTeam(body.user_id, body),
    onSuccess: () => {
      setTeamFor(null);
      setTeamId("");
      setMessage(bi("Added to team", "به تیم اضافه شد"));
      invalidateAdmin();
    },
    onError: (e) => setFormError(String((e as Error).message)),
  });

  const updateRole = useMutation({
    mutationFn: (body: { permission_codes: string[]; data_scope_level: string }) =>
      api.admin.updateRole(roleId, body),
    onSuccess: () => {
      setMessage(bi("Role saved", "نقش ذخیره شد"));
      void qc.invalidateQueries({ queryKey: ["admin", "role", roleId] });
    },
    onError: (e) => setFormError(String((e as Error).message)),
  });

  if (!isAdmin) {
    return (
      <>
        <PageHeader title={<Bi en="Organization admin" fa="مدیریت سازمان" />} />
        <Card>
          <Muted>
            <Bi
              en="You need the org.admin permission to manage users, roles and teams."
              fa="برای مدیریت کاربران، نقش‌ها و تیم‌ها به مجوز org.admin نیاز دارید."
            />
          </Muted>
        </Card>
      </>
    );
  }

  return (
    <>
      <PageHeader
        title={<Bi en="Organization admin" fa="مدیریت سازمان" />}
        description={
          <Bi
            en="Create users, deactivate accounts, reset a password, edit role permissions and add people to teams."
            fa="ساخت کاربر، غیرفعال‌سازی حساب، بازنشانی رمز، ویرایش مجوزهای نقش و افزودن اعضا به تیم."
          />
        }
      />
      <ErrorMessage error={formError || loadError} />

      <Card>
        <SectionHeader icon="plus" title={<Bi en="New user" fa="کاربر جدید" />} />
        <form className="form-grid" onSubmit={onSubmit}>
          <Field label={<Bi en="Full name" fa="نام کامل" />}>
            <Input value={name} onChange={(e) => setName(e.target.value)} required />
          </Field>
          <Field label={<Bi en="Email" fa="ایمیل" />}>
            <Input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </Field>
          <Field label={<Bi en="Password" fa="رمز عبور" />}>
            <Input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </Field>
          <div className="span-all">
            <Button type="submit">{bi("Create", "ساختن")}</Button>
          </div>
        </form>
      </Card>

      <Card padded={false}>
        <SectionHeader icon="users" title={<Bi en="People" fa="کاربران" />} count={people.length} />
        <Input value={userQuery} onChange={(e) => setUserQuery(e.target.value)} placeholder={bi("Search users", "جستجوی کاربر")} />
        {peopleQuery.isLoading ? (
          <LoadingState />
        ) : people.length === 0 ? (
          <EmptyState
            titleEn="No users yet"
            titleFa="هنوز کاربری نیست"
            bodyEn="Create the first account above."
            bodyFa="اولین حساب را بالا بسازید."
          />
        ) : (
          <Table
            rows={people}
            rowKey={(u) => String(u.id)}
            columns={[
              {
                key: "name",
                header: <Bi en="Name" fa="نام" />,
                render: (u) => (
                  <span className="cell-main">
                    <strong>{String(u.full_name)}</strong>
                    <Muted className="mono">{String(u.email)}</Muted>
                  </span>
                ),
              },
              {
                key: "active",
                header: <Bi en="Status" fa="وضعیت" />,
                render: (u) => (
                  <Bi
                    en={u.is_active ? "Active" : "Deactivated"}
                    fa={u.is_active ? "فعال" : "غیرفعال"}
                  />
                ),
              },
              {
                key: "actions",
                header: <Bi en="Actions" fa="عملیات" />,
                render: (u) => (
                  <span style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    <Button
                      variant="secondary"
                      disabled={updateUser.isPending}
                      onClick={() => {
                        void (async () => {
                          if (u.is_active) {
                            const ok = await confirm(
                              bi("Deactivate this user?", "این کاربر غیرفعال شود؟"),
                              bi("They will not be able to sign in.", "دیگر نمی‌تواند وارد شود."),
                              bi("Deactivate", "غیرفعال"),
                            );
                            if (!ok) return;
                          }
                          updateUser.mutate({
                            user_id: String(u.id),
                            is_active: !u.is_active,
                          });
                        })();
                      }}
                    >
                      {u.is_active
                        ? bi("Deactivate", "غیرفعال کردن")
                        : bi("Activate", "فعال کردن")}
                    </Button>
                    <Button
                      variant="secondary"
                      onClick={() => {
                        setFormError("");
                        setResetFor(resetFor === String(u.id) ? null : String(u.id));
                        setResetValue("");
                      }}
                    >
                      {bi("Reset password", "بازنشانی رمز")}
                    </Button>
                    <Button
                      variant="secondary"
                      onClick={() => {
                        setFormError("");
                        setTeamFor(teamFor === String(u.id) ? null : String(u.id));
                        setTeamId(String(u.team_id ?? teams[0]?.id ?? ""));
                      }}
                    >
                      {bi("Add to team", "افزودن به تیم")}
                    </Button>
                  </span>
                ),
              },
            ]}
          />
        )}
        {resetFor ? (
          <form
            className="form-grid"
            onSubmit={(e) => {
              e.preventDefault();
              resetPassword.mutate({ user_id: resetFor, password: resetValue });
            }}
          >
            <Field label={<Bi en="New password" fa="رمز جدید" />} className="span-all">
              <Input
                type="password"
                value={resetValue}
                onChange={(e) => setResetValue(e.target.value)}
                required
                autoFocus
              />
            </Field>
            <div className="span-all">
              <Button type="submit" disabled={resetPassword.isPending}>
                {bi("Save new password", "ذخیره رمز جدید")}
              </Button>
            </div>
          </form>
        ) : null}
        {teamFor ? (
          <form
            className="form-grid"
            onSubmit={(e) => {
              e.preventDefault();
              addTeam.mutate({ user_id: teamFor, team_id: teamId });
            }}
          >
            <Field label={<Bi en="Team" fa="تیم" />} className="span-all">
              <Select value={teamId} onChange={(e) => setTeamId(e.target.value)}>
                {teams.map((t) => (
                  <option key={String(t.id)} value={String(t.id)}>
                    {String(t.name)}
                  </option>
                ))}
              </Select>
            </Field>
            <div className="span-all">
              <Button type="submit" disabled={addTeam.isPending || !teamId}>
                {bi("Add to team", "افزودن به تیم")}
              </Button>
            </div>
          </form>
        ) : null}
      </Card>

      <Card>
        <SectionHeader icon="check" title={<Bi en="Role permissions" fa="مجوزهای نقش" />} />
        <div className="form-grid">
          <Field label={<Bi en="Role" fa="نقش" />} className="span-all">
            <Select value={roleId} onChange={(e) => setSelectedRole(e.target.value)}>
              {roles.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        {roleQuery.isLoading ? (
          <LoadingState />
        ) : roleQuery.isError ? (
          <ErrorMessage error={String((roleQuery.error as Error).message)} />
        ) : roleQuery.data ? (
          <RoleEditor
            codes={codesQuery.data ?? []}
            selected={roleQuery.data.permission_codes}
            scope={roleQuery.data.data_scope_level}
            busy={updateRole.isPending}
            onSave={(permission_codes, data_scope_level) =>
              updateRole.mutate({ permission_codes, data_scope_level })
            }
          />
        ) : null}
      </Card>
    </>
  );
}

function RoleEditor({
  codes,
  selected,
  scope,
  busy,
  onSave,
}: {
  codes: string[];
  selected: string[];
  scope: string | null;
  busy: boolean;
  onSave: (codes: string[], scope: string) => void;
}) {
  const bi = useBi();
  const [checked, setChecked] = useState<Set<string>>(() => new Set(selected));
  const [level, setLevel] = useState(scope || "organization");

  // Reset local edits whenever another role (or a saved state) is loaded.
  const signature = selected.join(",");
  const [seen, setSeen] = useState(signature);
  if (seen !== signature) {
    setSeen(signature);
    setChecked(new Set(selected));
    setLevel(scope || "organization");
  }

  function toggle(code: string) {
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  }

  return (
    <>
      <Field label={<Bi en="Data scope" fa="محدوده داده" />}>
        <Select value={level} onChange={(e) => setLevel(e.target.value)}>
          {SCOPES.map(([value, en, fa]) => (
            <option key={value} value={value}>
              {bi(en, fa)}
            </option>
          ))}
        </Select>
      </Field>
      <ul className="tag-list" style={{ marginTop: "var(--space-3)" }}>
        {codes.map((code) => (
          <li key={code}>
            <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <input
                type="checkbox"
                checked={checked.has(code)}
                onChange={() => toggle(code)}
              />
              <span className="mono" style={{ fontSize: "0.78rem" }}>
                {code}
              </span>
            </label>
          </li>
        ))}
      </ul>
      <div style={{ marginTop: "var(--space-3)" }}>
        <Button disabled={busy} onClick={() => onSave(Array.from(checked).sort(), level)}>
          {bi("Save role", "ذخیره نقش")}
        </Button>
      </div>
    </>
  );
}
