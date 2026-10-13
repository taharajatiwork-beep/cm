import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { api } from "./api";
import { useAuth } from "./auth";
import { Avatar, Icon, type IconName } from "./components/ui";
import { Bi, LangSwitch, useBi, useLocale } from "./i18n";
import { canSeeMarketingHome, canSeeNavPath, marketingHomePath } from "./lib/access";
import { dailyPaths, groupDailyNav, partitionMarketingNav } from "./lib/focus";
import { isPerformanceUser } from "./lib/navigation";
import { roleTitle } from "./lib/roles";
import { symbolUrl } from "./brand/logos";

type NavGroupKey = "" | "Marketing" | "More";

type NavItem = {
  to: string;
  icon: IconName;
  labelEn: string;
  labelFa: string;
  hintEn: string;
  hintFa: string;
  end?: boolean;
  perm?: string;
  permAny?: string[];
  adminOnly?: boolean;
  managerOnly?: boolean;
  group: NavGroupKey;
};

const navCatalog: NavItem[] = [
  { to: "/", icon: "home", labelEn: "Home", labelFa: "خانه", hintEn: "What needs you today", hintFa: "امروز چه چیزی به شما نیاز دارد", end: true, group: "" },
  { to: "/my-work", icon: "check", labelEn: "My Work", labelFa: "کارهای من", hintEn: "Things you need to do", hintFa: "کارهایی که باید انجام دهید", group: "" },
  { to: "/requests", icon: "send", labelEn: "Work requests", labelFa: "درخواست‌های کار", hintEn: "Manager work request → team projects", hintFa: "درخواست کار مدیر به تیم", end: true, permAny: ["request.create", "request.triage", "request.manage", "org.admin"], group: "" },
  { to: "/projects", icon: "layers", labelEn: "Projects", labelFa: "پروژه‌ها", hintEn: "One request, one or more projects", hintFa: "از هر درخواست یک یا چند پروژه", permAny: ["request.create", "request.triage", "request.manage", "task.read", "org.admin"], group: "" },
  { to: "/calendar", icon: "clock", labelEn: "Calendar", labelFa: "تقویم", hintEn: "Content and everyone's work", hintFa: "محتوا و کار همه", group: "" },
  { to: "/pricing", icon: "upload", labelEn: "Price and posts", labelFa: "قیمت و پست‌ها", hintEn: "Confirm the price before a post goes out", hintFa: "قیمت را قبل از پست تأیید کنید", group: "" },
  { to: "/communication", icon: "message", labelEn: "Messages", labelFa: "پیام‌ها", hintEn: "Talk with colleagues", hintFa: "گفتگو با همکاران", perm: "conversation.read", group: "" },
  { to: "/vehicles", icon: "car", labelEn: "Vehicles", labelFa: "خودروها", hintEn: "Cars in stock and their details", hintFa: "خودروهای موجود و مشخصاتشان", perm: "inventory.read", group: "" },
  { to: "/customers", icon: "user", labelEn: "Customers", labelFa: "مشتریان", hintEn: "Buyers and sellers", hintFa: "خریداران و فروشندگان", group: "" },
  { to: "/perf", icon: "activity", labelEn: "Performance", labelFa: "پرفورمنس", hintEn: "Perf campaigns, costs and results", hintFa: "کمپین پرفورمنس، هزینه و نتیجه", end: true, permAny: ["perf.read", "perf.write", "perf.approve", "price.approve"], group: "Marketing" },
  { to: "/perf/campaigns", icon: "megaphone", labelEn: "Perf campaigns", labelFa: "کمپین پرفورمنس", hintEn: "Cost, leads and CPL", hintFa: "هزینه، ورودی و هزینه هر ورودی", permAny: ["perf.read", "perf.write", "perf.approve", "price.approve"], group: "Marketing" },
  { to: "/perf/sms", icon: "message", labelEn: "SMS", labelFa: "پیامک", hintEn: "Write, lists and sends", hintFa: "نوشتن، لیست و ثبت ارسال", permAny: ["perf.read", "perf.write"], group: "Marketing" },
  { to: "/perf/social", icon: "flag", labelEn: "Social", labelFa: "سوشال", hintEn: "Cars, budget, then pages", hintFa: "ماشین، بودجه، بعد پیج", permAny: ["perf.read", "perf.write"], group: "Marketing" },
  { to: "/perf/sheet", icon: "layers", labelEn: "Sheet", labelFa: "شیت", hintEn: "Campaign rows and sync", hintFa: "ردیف کمپین و همگام‌سازی", group: "Marketing" },
  { to: "/perf/money", icon: "briefcase", labelEn: "Costs", labelFa: "هزینه‌ها", hintEn: "Charges and payments", hintFa: "شارژ و پرداخت", group: "" },
  { to: "/people", icon: "users", labelEn: "Colleagues", labelFa: "همکاران", hintEn: "Who does what", hintFa: "چه کسی چه کاری می‌کند", perm: "user.read", group: "More" },
  { to: "/knowledge", icon: "book", labelEn: "Rules & guides", labelFa: "قوانین و راهنماها", hintEn: "Company rules and how-tos", hintFa: "قوانین شرکت و روش انجام کارها", perm: "kb.read", group: "More" },
  { to: "/reports", icon: "activity", labelEn: "Reports", labelFa: "گزارش‌ها", hintEn: "Requests, projects, and campaign numbers", hintFa: "درخواست، پروژه و اعداد کمپین", group: "More" },
  { to: "/admin", icon: "settings", labelEn: "Admin", labelFa: "مدیریت", hintEn: "Overview, users, audit", hintFa: "نمای کلی، کاربران، ممیزی", perm: "org.admin", group: "More" },
];

const roleFa: Record<string, string> = {
  admin: "ادمین سایت",
  requester: "مدیر",
  lead: "سرپرست",
  member: "عضو",
  manager: "مدیر شعبه",
  seller: "فروشنده",
  marketing: "مارکتینگ",
  marketing_manager: "سرپرست مارکتینگ",
  performance_marketing: "پرفورمنس مارکتینگ",
  finance: "مالی",
  designer: "طراح",
  filmmaker: "فیلم‌بردار",
  reporter: "گزارش‌گیر",
  viewer: "بازدیدکننده",
};

function sortByDaily<T extends { to: string }>(items: T[], daily: string[]): T[] {
  const order = new Map(daily.map((path, index) => [path, index]));
  return [...items].sort((a, b) => (order.get(a.to) ?? 999) - (order.get(b.to) ?? 999));
}

function NavLinks({ items, closeDrawer, bi }: { items: NavItem[]; closeDrawer: () => void; bi: (en: string, fa: string) => string }) {
  return items.map((l) => (
    <NavLink key={l.to} to={l.to} end={l.end} title={bi(l.hintEn, l.hintFa)} onClick={closeDrawer}>
      <Icon name={l.icon} />
      <span>
        <Bi en={l.labelEn} fa={l.labelFa} />
      </span>
    </NavLink>
  ));
}

export function Shell() {
  const { user, logout, roleHint, has } = useAuth();
  const bi = useBi();
  const { locale } = useLocale();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const searchRef = useRef<HTMLInputElement>(null);
  const [q, setQ] = useState("");
  const [drawerAt, setDrawerAt] = useState<string | null>(null);
  if (drawerAt !== null && drawerAt !== pathname) setDrawerAt(null);
  const drawer = drawerAt === pathname;
  const toggleRef = useRef<HTMLButtonElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const wasOpen = useRef(false);
  const closeDrawer = () => setDrawerAt(null);
  const notes = useQuery({
    queryKey: ["notifications", "badge"],
    queryFn: () => api.notifications(),
    refetchInterval: 30_000,
  });
  const noteCount = (notes.data ?? []).filter((row) => !row.is_read).length;
  const roleLabel =
    locale === "fa" ? roleTitle(user?.roleCode, user?.branch_name) || roleFa[roleHint] || roleHint : user?.roleCode || roleHint;
  const isSiteAdmin = user?.roleCode === "admin" || has("org.admin");
  const isBranchManager = user?.roleCode === "manager" || isSiteAdmin;

  const accessUser = useMemo(
    () => ({
      roleCode: user?.roleCode,
      permissions: user?.permissions ?? [],
      teamId: user?.team_id,
      teamHomeTeamId: user?.team_home_team_id,
    }),
    [user?.roleCode, user?.permissions, user?.team_id, user?.team_home_team_id],
  );

  const visibleItems = useMemo(() => {
    const seen = new Set<string>();
    const homePath = marketingHomePath(accessUser);
    const injected: NavItem[] =
      homePath && canSeeMarketingHome(accessUser)
        ? [
            {
              to: homePath,
              icon: "flag",
              labelEn: "Marketing home",
              labelFa: "خانه مارکتینگ",
              hintEn: "How marketing is doing",
              hintFa: "وضعیت کلی مارکتینگ",
              group: "Marketing",
            },
          ]
        : [];
    const items = [...injected, ...navCatalog].filter((item) => {
      if (seen.has(item.to)) return false;
      if (item.adminOnly && !isSiteAdmin) return false;
      if (item.managerOnly && !isBranchManager) return false;
      const visible = canSeeNavPath(item.to, accessUser, has);
      if (visible) seen.add(item.to);
      return visible;
    });
    return items;
  }, [accessUser, has, isSiteAdmin, isBranchManager]);

  const focusUser = useMemo(
    () => ({
      roleHint,
      roleCode: user?.roleCode,
      permissions: user?.permissions ?? [],
      teamId: user?.team_id,
      teamHomeTeamId: user?.team_home_team_id,
    }),
    [roleHint, user?.roleCode, user?.permissions, user?.team_id, user?.team_home_team_id],
  );

  const daily = useMemo(() => dailyPaths(focusUser), [focusUser]);
  const marketingHomeTo = marketingHomePath(accessUser);
  const navForGeneral = useMemo(
    () =>
      visibleItems.filter(
        (item) => item.group !== "Marketing" && (!marketingHomeTo || item.to !== marketingHomeTo),
      ),
    [visibleItems, marketingHomeTo],
  );
  const placed = useMemo(() => groupDailyNav(navForGeneral, daily), [navForGeneral, daily]);
  const mainNav = useMemo(() => sortByDaily(placed.main, daily), [placed.main, daily]);
  const otherMore = placed.more;

  const marketingNav = useMemo(
    () => partitionMarketingNav(visibleItems, marketingHomeTo),
    [visibleItems, marketingHomeTo],
  );

  const perfFocused =
    isPerformanceUser({ roleCode: user?.roleCode, permissions: user?.permissions ?? [] }) || roleHint === "marketing";

  const perfToolsPathActive = marketingNav.perfTools.some(
    (item) => pathname === item.to || pathname.startsWith(`${item.to}/`),
  );
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);

  useEffect(() => {
    if (!drawer) {
      if (wasOpen.current) toggleRef.current?.focus();
      wasOpen.current = false;
      return;
    }
    wasOpen.current = true;
    closeRef.current?.focus();
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setDrawerAt(null);
    };
    const wide = window.matchMedia("(min-width: 861px)");
    const onWide = () => {
      if (wide.matches) setDrawerAt(null);
    };
    window.addEventListener("keydown", onKey);
    wide.addEventListener("change", onWide);
    return () => {
      document.body.style.overflow = overflow;
      window.removeEventListener("keydown", onKey);
      wide.removeEventListener("change", onWide);
    };
  }, [drawer]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        searchRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  function onSearch(e: FormEvent) {
    e.preventDefault();
    const query = q.trim();
    navigate(query ? `/search?q=${encodeURIComponent(query)}` : "/search");
  }

  return (
    <div className={`app-shell${drawer ? " nav-open" : ""}`}>
      {drawer ? (
        <button type="button" className="nav-backdrop" tabIndex={-1} aria-hidden onClick={closeDrawer} />
      ) : null}
      <aside
        className="nav"
        id="app-nav"
        aria-label={bi("Main menu", "منوی اصلی")}
        {...(drawer ? { role: "dialog", "aria-modal": true } : {})}
      >
        <div className="brand-row">
          <Link to="/" className="brand">
            <img className="brand-mark" src={symbolUrl} alt="" width={96} height={69} />
            <span className="brand-text">
              <strong>
                <Bi en="Sotoodeh" fa="ستوده" />
              </strong>
              <span>
                <Bi en="Operations" fa="سامانه عملیاتی" />
              </span>
            </span>
          </Link>
          <button
            ref={closeRef}
            type="button"
            className="icon-btn nav-close"
            onClick={closeDrawer}
            aria-label={bi("Close menu", "بستن منو")}
            title={bi("Close menu", "بستن منو")}
          >
            <Icon name="x" />
          </button>
        </div>

        <nav className="nav-primary">
          {mainNav.length > 0 ? (
            <div className="nav-group">
              <div className="nav-group-label">
                <Bi en="General" fa="عمومی" />
              </div>
              <NavLinks items={mainNav} closeDrawer={closeDrawer} bi={bi} />
            </div>
          ) : null}

          {marketingNav.head.length > 0 || marketingNav.perfTools.length > 0 ? (
            <div className="nav-group">
              <div className="nav-group-label">
                <Bi en="Marketing" fa="مارکتینگ" />
              </div>
              {marketingNav.head.length > 0 ? (
                <NavLinks items={marketingNav.head} closeDrawer={closeDrawer} bi={bi} />
              ) : null}
              {marketingNav.perfTools.length > 0 ? (
                <details className="advanced nav-advanced" open={perfFocused || perfToolsPathActive || undefined}>
                  <summary>
                    <Bi en="Performance tools" fa="ابزارهای پرفورمنس" />
                  </summary>
                  <div className="nav-group nav-group--nested">
                    <NavLinks items={marketingNav.perfTools} closeDrawer={closeDrawer} bi={bi} />
                  </div>
                </details>
              ) : null}
            </div>
          ) : null}

          {otherMore.length > 0 ? (
            <details className="advanced nav-advanced" open>
              <summary>
                <Bi en="More" fa="بیشتر" />
              </summary>
              <div className="nav-group nav-group--nested">
                <NavLinks items={otherMore} closeDrawer={closeDrawer} bi={bi} />
              </div>
            </details>
          ) : null}
        </nav>

        <div className="nav-footer">
          <NavLink to="/settings" className="nav-settings" onClick={closeDrawer}>
            <Icon name="settings" />
            <span>
              <Bi en="Settings" fa="تنظیمات" />
            </span>
          </NavLink>
          {(has("campaign.read") || has("perf.read") || has("perf.write") || has("perf.approve") || has("price.approve") || has("price.write")) ? (
            <NavLink to="/perf/connections" className="nav-settings" onClick={closeDrawer} title={bi("The tools you use", "ابزارهای خودتان")}>
              <Icon name="plug" />
              <span>
                <Bi en="Connections" fa="اتصالات" />
              </span>
            </NavLink>
          ) : null}
          <div className="user-chip">
            <Avatar name={user?.full_name || user?.email || "?"} size={30} />
            <div className="user-chip-text">
              <strong>{user?.full_name}</strong>
              <span>{roleLabel}</span>
            </div>
            <button
              type="button"
              className="icon-btn"
              onClick={logout}
              title={bi("Sign out", "خروج")}
              aria-label={bi("Sign out", "خروج")}
            >
              <Icon name="logout" />
            </button>
          </div>
        </div>
      </aside>

      <div className="shell-main" inert={drawer || undefined}>
        <header className="shell-top">
          <button
            ref={toggleRef}
            type="button"
            className="icon-btn nav-toggle"
            onClick={() => setDrawerAt(drawer ? null : pathname)}
            aria-label={bi("Menu", "منو")}
            title={bi("Menu", "منو")}
            aria-expanded={drawer}
            aria-controls="app-nav"
          >
            <Icon name="menu" size={18} />
          </button>
          <form className="global-search" onSubmit={onSearch} role="search">
            <Icon name="search" className="global-search-icon" />
            <input
              ref={searchRef}
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder={bi("Find a car, customer, colleague…", "پیدا کردن خودرو، مشتری، همکار…")}
              aria-label={bi("Search", "جستجو")}
            />
            <kbd>Ctrl K</kbd>
          </form>
          <div className="shell-top-actions">
            <Link to="/agent" className="top-ai">
              <Icon name="sparkles" />
              <span>
                <Bi en="Ask the assistant" fa="از دستیار بپرس" />
              </span>
            </Link>
            <LangSwitch />
            <Link
              className="icon-btn bell"
              to="/notifications"
              title={bi("Notifications", "اعلان‌ها")}
              aria-label={bi("Notifications", "اعلان‌ها")}
            >
              <Icon name="bell" />
              {noteCount > 0 && (
                <span className="bell-badge">{noteCount > 9 ? "9+" : noteCount}</span>
              )}
            </Link>
          </div>
        </header>
        <main className="main">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
