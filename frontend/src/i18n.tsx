/* Provider file intentionally exports hooks beside its component. */
/* eslint-disable react/only-export-components */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type Locale = "en" | "fa";

const STORAGE_KEY = "cm-locale";

type LocaleCtx = {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (en: string, fa: string) => string;
};

const LocaleContext = createContext<LocaleCtx | null>(null);

function readStoredLocale(): Locale {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v === "en" || v === "fa") return v;
  } catch {
    /* ignore */
  }
  return "fa";
}

export function LocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(readStoredLocale);

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
  }, []);

  useEffect(() => {
    document.documentElement.lang = locale;
    document.documentElement.dir = locale === "fa" ? "rtl" : "ltr";
    try {
      localStorage.setItem(STORAGE_KEY, locale);
    } catch {
      /* ignore */
    }
  }, [locale]);

  const t = useCallback((en: string, fa: string) => (locale === "fa" ? fa : en), [locale]);

  const value = useMemo(() => ({ locale, setLocale, t }), [locale, setLocale, t]);

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useLocale(): LocaleCtx {
  const ctx = useContext(LocaleContext);
  if (!ctx) throw new Error("useLocale must be used within LocaleProvider");
  return ctx;
}

/** Hook returning a translator: bi("English", "فارسی") */
export function useBi(): (en: string, fa: string) => string {
  return useLocale().t;
}

export function Bi({ en, fa }: { en: string; fa: string }) {
  const { t } = useLocale();
  return <>{t(en, fa)}</>;
}

export function LangSwitch({ className = "" }: { className?: string }) {
  const { locale, setLocale, t } = useLocale();

  return (
    <div
      className={`lang-switch ${className}`.trim()}
      role="group"
      aria-label={t("Language", "زبان")}
    >
      <button
        type="button"
        className={locale === "en" ? "active" : ""}
        onClick={() => setLocale("en")}
        aria-pressed={locale === "en"}
      >
        EN
      </button>
      <button
        type="button"
        className={locale === "fa" ? "active" : ""}
        onClick={() => setLocale("fa")}
        aria-pressed={locale === "fa"}
      >
        FA
      </button>
    </div>
  );
}
