import type { Scenario } from "./lib/types";

/** سناریوهای synthetic user — گام ثابت + عامل LLM اختیاری. */
export const SCENARIOS: Scenario[] = [
  {
    id: "requester-home-requests",
    personaFile: "ali-requester.md",
    loginEmail: "ali@autoco.example",
    missionFa: "بفهمم درخواست‌های کارم کجاست و لیست را ببینم.",
    successCriteriaFa: "به صفحه درخواست‌های کار رسیدم و عنوان/فهرست قابل تشخیص است.",
    steps: [
      { kind: "note", text: "بعد از ورود اول سراغ خانه می‌روم ببینم چه چیزی منتظر من است." },
      { kind: "expectVisible", role: "link", name: "خانه" },
      { kind: "click", role: "link", name: "درخواست‌های کار" },
      { kind: "expectVisible", role: "heading", name: "درخواست‌های کار" },
    ],
    maxLlmSteps: 8,
  },
  {
    id: "seller-my-work",
    personaFile: "reza-seller.md",
    loginEmail: "reza@autoco.example",
    missionFa: "کارهای امروزم را در «کارهای من» پیدا کنم.",
    successCriteriaFa: "صفحه کارهای من باز شد.",
    steps: [
      { kind: "click", role: "link", name: "کارهای من" },
      { kind: "expectVisible", role: "heading", name: "کارهای من" },
    ],
    maxLlmSteps: 6,
  },
  {
    id: "seller-vehicles",
    personaFile: "reza-seller.md",
    loginEmail: "reza@autoco.example",
    missionFa: "لیست خودروهای موجود را ببینم.",
    successCriteriaFa: "صفحه خودروها با عنوان قابل تشخیص باز شد.",
    steps: [
      { kind: "click", role: "link", name: "خودروها" },
      { kind: "expectVisible", role: "heading", name: "خودرو" },
    ],
    maxLlmSteps: 6,
  },
  {
    id: "marketing-manager-projects",
    personaFile: "mina-marketing-manager.md",
    loginEmail: "mina@autoco.example",
    missionFa: "پروژه‌های جاری تیم را از منو باز کنم.",
    successCriteriaFa: "صفحه پروژه‌ها با فهرست یا عنوان پروژه دیده می‌شود.",
    steps: [
      { kind: "goto", path: "/projects" },
      { kind: "expectVisible", name: "پروژه" },
    ],
    maxLlmSteps: 6,
  },
  {
    id: "marketing-manager-triage-queue",
    personaFile: "mina-marketing-manager.md",
    loginEmail: "mina@autoco.example",
    missionFa: "صف درخواست‌های ورودی تیم را ببینم.",
    successCriteriaFa: "بخش «صف درخواست‌ها» روی صفحه درخواست‌ها دیده می‌شود.",
    steps: [
      { kind: "click", role: "link", name: "درخواست‌های کار" },
      { kind: "expectVisible", role: "heading", name: "صف درخواست" },
    ],
    maxLlmSteps: 8,
  },
  {
    id: "marketing-manager-calendar",
    personaFile: "mina-marketing-manager.md",
    loginEmail: "mina@autoco.example",
    missionFa: "تقویم محتوا و کار تیم را باز کنم.",
    successCriteriaFa: "صفحه تقویم با نام ماه یا عنوان تقویم دیده می‌شود.",
    steps: [
      { kind: "note", text: "تقویم اغلب زیر «بیشتر» است؛ مستقیم می‌روم تا گم نشود." },
      { kind: "goto", path: "/calendar" },
      { kind: "expectVisible", name: "تقویم" },
    ],
    maxLlmSteps: 6,
  },
  {
    id: "marketing-pricing",
    personaFile: "sara-marketing.md",
    loginEmail: "sara@autoco.example",
    missionFa: "صفحه قیمت و پست‌های امروز را پیدا کنم.",
    successCriteriaFa: "صفحه قیمت و پست‌ها باز شد.",
    steps: [
      { kind: "click", role: "link", name: "قیمت و پست" },
      { kind: "expectVisible", role: "heading", name: "قیمت" },
    ],
    maxLlmSteps: 6,
  },
  {
    id: "performance-campaigns",
    personaFile: "nadia-performance.md",
    loginEmail: "nadia@autoco.example",
    missionFa: "لیست کمپین‌های پرفورمنس را ببینم.",
    successCriteriaFa: "به بخش کمپین پرفورمنس رسیدم.",
    steps: [
      { kind: "click", role: "link", name: "کمپین پرفورمنس" },
      { kind: "expectVisible", role: "heading", name: "کمپین" },
    ],
    maxLlmSteps: 8,
  },
  {
    id: "performance-sheet",
    personaFile: "nadia-performance.md",
    loginEmail: "nadia@autoco.example",
    missionFa: "شیت کمپین را برای همگام‌سازی باز کنم.",
    successCriteriaFa: "صفحه شیت با عنوان شیت دیده می‌شود.",
    steps: [
      { kind: "goto", path: "/perf/sheet" },
      { kind: "expectVisible", name: "شیت" },
    ],
    maxLlmSteps: 8,
  },
  {
    id: "finance-money",
    personaFile: "finance.md",
    loginEmail: "finance@autoco.example",
    missionFa: "هزینه‌ها و درخواست‌های پرداخت را ببینم.",
    successCriteriaFa: "صفحه هزینه‌ها در پرفورمنس باز شد.",
    steps: [
      { kind: "note", text: "لینک هزینه در منوی جمع‌شده است؛ مسیر مستقیم را امتحان می‌کنم." },
      { kind: "goto", path: "/perf/money" },
      { kind: "expectVisible", role: "heading", name: "هزینه" },
    ],
    maxLlmSteps: 6,
  },
  {
    id: "reporter-reports",
    personaFile: "reporter.md",
    loginEmail: "reporter@autoco.example",
    missionFa: "گزارش کار و اعداد تیم را ببینم.",
    successCriteriaFa: "صفحه گزارش‌ها باز شد.",
    steps: [
      { kind: "click", role: "link", name: "گزارش" },
      { kind: "expectVisible", role: "heading", name: "گزارش" },
    ],
    maxLlmSteps: 6,
  },
  {
    id: "mashhad-requester-requests",
    personaFile: "maryam-requester.md",
    loginEmail: "maryam@autoco.example",
    missionFa: "درخواست‌های شعبه را ثبت/پیگیری کنم.",
    successCriteriaFa: "صفحه درخواست‌های کار برای مدیر شعبه در دسترس است.",
    steps: [
      { kind: "click", role: "link", name: "درخواست‌های کار" },
      { kind: "expectVisible", role: "heading", name: "درخواست‌های کار" },
    ],
    maxLlmSteps: 6,
  },
  {
    id: "admin-organization",
    personaFile: "admin.md",
    loginEmail: "admin@autoco.example",
    missionFa: "پنل مدیریت سازمان را باز کنم.",
    successCriteriaFa: "صفحه مدیریت سازمان دیده می‌شود.",
    steps: [
      { kind: "click", role: "link", name: "مدیریت" },
      { kind: "expectVisible", role: "heading", name: "مدیریت" },
    ],
    maxLlmSteps: 6,
  },
];

export function getScenario(id: string): Scenario | undefined {
  return SCENARIOS.find((s) => s.id === id);
}
