import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { api } from "./api";
import { useAuth } from "./auth";
import { Avatar, Icon, type IconName } from "./components/ui";
import { Bi, LangSwitch, useBi, useLocale } from "./i18n";

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
};

const navGroups: Array<{ en: string; fa: string; items: NavItem[] }> = [
  {
    en: "",
    fa: "",
    items: [
      { to: "/", icon: "home", labelEn: "Home", labelFa: "خانه", hintEn: "What needs you today", hintFa: "امروز چه چیزی به شما نیاز دارد", end: true },
      { to: "/my-work", icon: "check", labelEn: "My Work", labelFa: "کارهای من", hintEn: "Things you need to do", hintFa: "کارهایی که باید انجام دهید" },
      { to: "/pricing", icon: "megaphone", labelEn: "Price and posts", labelFa: "قیمت و پست‌ها", hintEn: "Confirm the price before a post goes out", hintFa: "قیمت را قبل از پست تأیید کنید", permAny: ["price.write", "campaign.read"] },
      { to: "/communication", icon: "message", labelEn: "Messages", labelFa: "پیام‌ها", hintEn: "Talk with colleagues", hintFa: "گفتگو با همکاران", perm: "conversation.read" },
      { to: "/vehicles", icon: "car", labelEn: "Vehicles", labelFa: "خودروها", hintEn: "Cars in stock and their details", hintFa: "خودروهای موجود و مشخصاتشان", perm: "inventory.read" },
      { to: "/approvals", icon: "check", labelEn: "Approvals", labelFa: "تأییدها", hintEn: "Requests waiting for a decision", hintFa: "درخواست‌هایی که منتظر تصمیم‌اند", perm: "price.write" },
      { to: "/customers", icon: "user", labelEn: "Customers", labelFa: "مشتریان", hintEn: "Buyers and sellers", hintFa: "خریداران و فروشندگان", adminOnly: true },
      { to: "/agent", icon: "sparkles", labelEn: "Assistant", labelFa: "دستیار", hintEn: "Ask about your own work", hintFa: "درباره کار خودتان بپرسید" },
    ],
  },
  {
    en: "Performance",
    fa: "پرفورمنس",
    items: [
      { to: "/perf", icon: "activity", labelEn: "Performance home", labelFa: "خانه پرفورمنس", hintEn: "Today's campaigns and balances", hintFa: "کمپین و موجودی امروز", end: true, permAny: ["perf.read", "perf.write", "perf.approve", "price.write"] },
      { to: "/perf/campaigns", icon: "megaphone", labelEn: "Campaigns", labelFa: "کمپین‌ها", hintEn: "Cost, leads and CPL", hintFa: "هزینه، ورودی و هزینه هر ورودی", permAny: ["perf.read", "perf.write", "perf.approve", "price.write"] },
      { to: "/perf/sms", icon: "message", labelEn: "SMS", labelFa: "پیامک", hintEn: "Write, lists and sends", hintFa: "نوشتن، لیست و ثبت ارسال", permAny: ["perf.read", "perf.write"] },
      { to: "/perf/social", icon: "flag", labelEn: "Social", labelFa: "سوشال", hintEn: "Cars, budget, then pages", hintFa: "ماشین، بودجه، بعد پیج", permAny: ["perf.read", "perf.write"] },
      { to: "/perf/money", icon: "briefcase", labelEn: "Money", labelFa: "پول", hintEn: "Charges and payments", hintFa: "شارژ و پرداخت", permAny: ["perf.read", "perf.write", "perf.approve", "price.write"] },
      { to: "/perf/sheet", icon: "book", labelEn: "Sheet", labelFa: "شیت", hintEn: "The live cost and result sheet", hintFa: "شیت زنده هزینه و نتیجه", permAny: ["perf.read", "perf.write", "perf.approve", "price.write"] },
      { to: "/perf/connections", icon: "settings", labelEn: "Connections", labelFa: "اتصالات", hintEn: "Sheets, Mizito and the rest", hintFa: "شیت، میزیتو و بقیه", permAny: ["perf.read", "perf.write", "perf.approve", "price.write"] },
    ],
  },
  {
    en: "More",
    fa: "بیشتر",
    items: [
      { to: "/people", icon: "users", labelEn: "Colleagues", labelFa: "همکاران", hintEn: "Who does what", hintFa: "چه کسی چه کاری می‌کند", perm: "user.read", managerOnly: true },
      { to: "/knowledge", icon: "book", labelEn: "Rules & guides", labelFa: "قوانین و راهنماها", hintEn: "Company rules and how-tos", hintFa: "قوانین شرکت و روش انجام کارها", adminOnly: true },
      { to: "/cases", icon: "briefcase", labelEn: "Cases", labelFa: "پرونده‌ها", hintEn: "Track one subject in your section", hintFa: "پیگیری یک موضوع در بخش شما", perm: "case.read", adminOnly: true },
      { to: "/reports", icon: "activity", labelEn: "Reports", labelFa: "گزارش‌ها", hintEn: "KPIs", hintFa: "شاخص‌ها", perm: "event.read", adminOnly: true },
      { to: "/admin", icon: "settings", labelEn: "Admin", labelFa: "مدیریت", hintEn: "Overview, users, audit", hintFa: "نمای کلی، کاربران، ممیزی", perm: "org.admin" },
    ],
  },
];

const roleFa: Record<string, string> = {
  admin: "ادمین سایت",
  manager: "مدیر",
  seller: "فروشنده",
  marketing: "بازاریابی",
  finance: "مالی",
  viewer: "بازدیدکننده",
  performance_marketing: "پرفورمنس",
  marketing_manager: "مدیر مارکتینگ",
};

export function Shell() {
  const { user, logout, roleHint, has } = useAuth();
  const bi = useBi();
  const { locale } = useLocale();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const searchRef = useRef<HTMLInputElement>(null);
  const [q, setQ] = useState("");
  const [drawer, setDrawer] = useState(false);
  const notes = useQuery({
    queryKey: ["notifications", "badge"],
    queryFn: () => api.notifications(),
    refetchInterval: 30_000,
  });
  const departments = useQuery({
    queryKey: ["departments"],
    queryFn: () => api.departments.list(),
    enabled: Boolean(user?.id),
  });
  const sectionName = String(
    (departments.data ?? []).find((row) => String(row.id) === String(user?.department_id))?.name ?? "",
  );
  const noteCount = (notes.data ?? []).filter((row) => !row.is_read).length;
  const roleLabel =
    locale === "fa"
      ? roleFa[user?.roleCode || ""] || roleFa[roleHint] || roleHint
      : user?.roleCode || roleHint;
  const orderedGroups =
    user?.roleCode === "performance_marketing"
      ? [...navGroups].sort((a, b) => Number(b.en === "Performance") - Number(a.en === "Performance"))
      : navGroups;

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);

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
      <button type="button" className="nav-toggle" onClick={() => setDrawer((v) => !v)} aria-label={bi("Menu", "منو")}>
        <Bi en="Menu" fa="منو" />
      </button>
      <aside className="nav">
        <Link to="/" className="brand">
          <span className="brand-mark">CM</span>
          <span className="brand-text">
            <strong>
              <Bi en="CM Ops" fa="عملیات CM" />
            </strong>
            <span>
              <Bi en="Automotive workspace" fa="فضای کار خودرو" />
            </span>
          </span>
        </Link>

        <nav className="nav-primary">
          {orderedGroups.map((g) => {
            const items = g.items.filter((l) => {
              if (l.adminOnly && roleHint !== "admin") return false;
              if (l.managerOnly && roleHint !== "manager" && roleHint !== "admin") return false;
              if (l.permAny) return l.permAny.some((code) => has(code));
              return !l.perm || has(l.perm);
            });
            if (items.length === 0) return null;
            return (
              <div className="nav-group" key={g.en || "main"}>
                {g.en ? (
                  <div className="nav-group-label">
                    <Bi en={g.en} fa={g.fa} />
                  </div>
                ) : null}
                {items.map((l) => (
                  <NavLink key={l.to} to={l.to} end={l.end} title={bi(l.hintEn, l.hintFa)} onClick={() => setDrawer(false)}>
                    <Icon name={l.icon} />
                    <span>
                      <Bi en={l.labelEn} fa={l.labelFa} />
                    </span>
                  </NavLink>
                ))}
              </div>
            );
          })}
        </nav>

        <div className="nav-footer">
          <NavLink to="/settings" className="nav-settings">
            <Icon name="settings" />
            <span>
              <Bi en="Settings" fa="تنظیمات" />
            </span>
          </NavLink>
          <div className="user-chip">
            <Avatar name={user?.full_name || user?.email || "?"} size={30} />
            <div className="user-chip-text">
              <strong>{user?.full_name}</strong>
              <span>{sectionName ? `${sectionName} · ${roleLabel}` : roleLabel}</span>
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

      <div className="shell-main">
        <header className="shell-top">
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
