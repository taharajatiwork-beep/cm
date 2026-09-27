import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
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
};

const navGroups: Array<{ en: string; fa: string; items: NavItem[] }> = [
  {
    en: "",
    fa: "",
    items: [
      { to: "/", icon: "home", labelEn: "Home", labelFa: "خانه", hintEn: "What needs you today", hintFa: "امروز چه چیزی به شما نیاز دارد", end: true },
      { to: "/my-work", icon: "check", labelEn: "My Work", labelFa: "کارهای من", hintEn: "Things you need to do", hintFa: "کارهایی که باید انجام دهید" },
      { to: "/communication", icon: "message", labelEn: "Messages", labelFa: "پیام‌ها", hintEn: "Talk with colleagues", hintFa: "گفتگو با همکاران" },
      { to: "/vehicles", icon: "car", labelEn: "Vehicles", labelFa: "خودروها", hintEn: "Cars in stock and their details", hintFa: "خودروهای موجود و مشخصاتشان" },
      { to: "/customers", icon: "user", labelEn: "Customers", labelFa: "مشتریان", hintEn: "Buyers and sellers", hintFa: "خریداران و فروشندگان" },
      { to: "/agent", icon: "sparkles", labelEn: "Assistant", labelFa: "دستیار", hintEn: "Ask anything in plain words", hintFa: "هر سؤالی را ساده بپرسید" },
    ],
  },
  {
    en: "More",
    fa: "بیشتر",
    items: [
      { to: "/people", icon: "users", labelEn: "Colleagues", labelFa: "همکاران", hintEn: "Who does what", hintFa: "چه کسی چه کاری می‌کند" },
      { to: "/knowledge", icon: "book", labelEn: "Rules & guides", labelFa: "قوانین و راهنماها", hintEn: "Company rules and how-tos", hintFa: "قوانین شرکت و روش انجام کارها" },
    ],
  },
];

const roleFa: Record<string, string> = {
  admin: "مدیر سیستم",
  manager: "مدیر",
  seller: "فروشنده",
  marketing: "بازاریابی",
  viewer: "بازدیدکننده",
};

export function Shell() {
  const { user, logout, roleHint } = useAuth();
  const bi = useBi();
  const { locale } = useLocale();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [noteCount, setNoteCount] = useState(0);
  const searchRef = useRef<HTMLInputElement>(null);
  const roleLabel = locale === "fa" ? roleFa[roleHint] || roleHint : roleHint;

  useEffect(() => {
    void api
      .notifications()
      .then((n) => setNoteCount(n.length))
      .catch(() => setNoteCount(0));
  }, []);

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
    <div className="app-shell">
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
          {navGroups.map((g) => (
            <div className="nav-group" key={g.en || "main"}>
              {g.en ? (
                <div className="nav-group-label">
                  <Bi en={g.en} fa={g.fa} />
                </div>
              ) : null}
              {g.items.map((l) => (
                <NavLink key={l.to} to={l.to} end={l.end} title={bi(l.hintEn, l.hintFa)}>
                  <Icon name={l.icon} />
                  <span>
                    <Bi en={l.labelEn} fa={l.labelFa} />
                  </span>
                </NavLink>
              ))}
            </div>
          ))}
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
