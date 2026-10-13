# توضیح کامل پروژه CM

**منبع اصلی نمای کلی.** بقیهٔ مستندات به این صفحه یا به کد/seed لینک می‌دهند.

سامانهٔ عملیاتی و ارتباطی برای شرکت‌های خودرویی چندشعبه‌ای — با تمرکز روی تبدیل گفتگو و کارهای پراکنده به کارهای ساختاریافته، قابل‌پیگیری و قابل‌واگذاری.

## فهرست مستندات

| سند | محتوا |
|-----|--------|
| [vocabulary.md](vocabulary.md) | نام‌های UI (درخواست کار، کمپین پرفورمنس، …) |
| [roles-plan.md](roles-plan.md) | نقش‌ها و مجوزها |
| [unification-plan.md](unification-plan.md) | یکپارچه‌سازی درخواست/پروژه |
| [adr/](adr/) | تصمیم‌های معماری |
| [llm-data-audit.md](llm-data-audit.md) | دادهٔ خروجی به LLM |
| [team-tree.html](team-tree.html) | درخت تیم (با seed هم‌خوان شود) |
| [requester-experience.md](requester-experience.md) | دید درخواست‌دهنده و فید خانه |
| [cm-flowchart.html](cm-flowchart.html) · [performance-flowchart.html](performance-flowchart.html) | جریان‌ها |

### ناسازگاری‌های شناخته‌شده (رفتار فعلی)

- **`/approvals`:** به `/my-work` ریدایرکت؛ تأییدهای سازمانی همان‌جا.
- **مشتریان در منو:** فقط `org.admin`؛ فروش با `case.read` پرونده می‌بیند، نه لیست CRM — [`requester-experience.md`](requester-experience.md).
- **دیتابیس:** فقط Postgres (لوکال: `docker compose`). ADR [`004-sqlite-retirement.md`](adr/004-sqlite-retirement.md).

---

## ۱. این پروژه چیست؟

**CM** (Automotive Communication & Operations Platform) یک پلتفرم **داخلی** برای عملیات فروش، موجودی، بازاریابی و هماهنگی شعب است.

### مشکلی که حل می‌کند

در شرکت‌های خودرویی معمولاً کارها در واتساپ، تماس و ذهن افراد پخش می‌شود:

- مشخص نیست «این خودرو» الان دست کیست و چه کسی باید مشتری را پیگیری کند
- بازاریابی و فروش روی یک هدف مشترک هماهنگ نمی‌شوند
- مهلت‌ها و SLA گم می‌شود
- مدیر باید افراد را دنبال کند تا بداند کار جلو رفته یا نه

### راه‌حل CM

کار غیررسمی را به موجودیت‌های رسمی تبدیل می‌کند:

| مفهوم کاربر | معنی |
|-------------|------|
| **کار مشترک** (Work Item) | هدف مشترکی که چند نفر با هم جلو می‌برند |
| **وظیفه** (Task) | یک اقدام مشخص با مسئول و مهلت |
| **پیگیری** (Case / Follow-up) | موضوعی که باید رصد شود (علاقه مشتری، درخواست شعبه، …) |
| **گفتگو** (Conversation) | بحث دربارهٔ کار — ترجیحاً متصل به کار مشترک یا **موضوع گفتگو** |
| **کمپین پرفورمنس** (`pm_campaign`) | اجرای تبلیغ با کد S…، هزینه و شیت — جدا از **موضوع گفتگو** (`campaigns`) |

واژه‌های کامل UI: [vocabulary.md](vocabulary.md).

اصل معماری: **دیتابیس منبع حقیقت است**؛ تلگرام، دیوار و مدل زبانی فقط واسط یا کمک‌کننده هستند — موجودیت جعلی نمی‌سازند.

---

## ۲. مخاطب و نقش‌ها

| نقش | نمونه دمو | کار روزمره |
|-----|-----------|------------|
| مدیر (`requester`) | `ali@autoco.example` | ثبت درخواست، قیمت و پست‌ها، گزارش خودش؛ پروژهٔ ساخته‌شده را **فقط‌خواندنی** می‌بیند |
| فروش (`seller`) | `reza@autoco.example` | وظایف، خودرو، پیام، **پرونده** (`case.read`) — نه منوی مشتریان |
| بازاریابی (`marketing`) | `sara@autoco.example` | تیم MKT_T، موضوع گفتگو، قیمت و پست‌ها |
| سرپرست مارکتینگ (`marketing_manager`) | `mina@autoco.example` | تریاژ، پروژه، تقویم (اسکوپ تیم)، کمپین پرفورمنس + شیت؛ **بدون** `request.create` |
| پرفورمنس (`performance_marketing`) | `nadia@autoco.example` | اجرای کمپین، تقویم با `perf.write`؛ **بدون** منوی پروژه‌ها |
| طراح / فیلم‌بردار | `leila@` / `kamran@` | نقش‌های `designer` / `filmmaker` روی MKT_DESIGN / MKT_FILM |
| گزارش‌گیر (`reporter`) | `reporter@autoco.example` | `report.read` در تیم مارکتینگ |
| مالی (`finance`) | `finance@autoco.example` | `price.approve` و `expense.pay`؛ قیمت/پست و `/perf/money` |
| ادمین | `admin@autoco.example` | کاربران، نقش‌ها، ساختار تیم‌ها، مشتریان، دید کامل |
| بازدیدکننده | `viewer@autoco.example` | فقط مشاهدهٔ محدود |
| شعبه دیگر | `maryam@autoco.example` | مدیر شعبهٔ مشهد؛ درخواست بدون تیم |

رمز همهٔ حساب‌های دمو: `password`  
سازمان دمو: `autoco`  
درخت تیم و grantها: [`team-tree.html`](team-tree.html) · خلاصهٔ نقش‌ها: [`roles-plan.md`](roles-plan.md)

---

## ۳. ساختار مخزن (Monorepo)

```text
cm/
├── README.md                 # شروع سریع
├── docs/                     # مستندات تخصصی + این فایل + ارائه
├── backend/                  # API (FastAPI)
│   ├── app/
│   │   ├── api/routes/       # HTTP هسته (org، work، pricing، telegram، enterprise، …)
│   │   ├── perf/             # پرفورمنس مارکتینگ: مسیرها، مدل‌ها، سرویس‌ها
│   │   ├── calendar/         # تقویم محتوا و کار (/calendar)
│   │   ├── requests/         # درخواست کار و پروژه (جدا از perf)
│   │   ├── services/         # منطق دامنه (audit، notifications، org، work، sla، …)
│   │   ├── models/           # SQLAlchemy (+ جداول تلگرام)
│   │   ├── ai/               # عامل‌ها و ابزارها
│   │   ├── integrations/     # تلگرام/باله، دیوار، …
│   │   │   └── telegram/     # client، adapter، outbox، polling
│   │   └── core/             # تنظیمات، مجوزها، امنیت، تقویم
│   ├── alembic/              # مایگریشن (تا 0031 تقویم محتوا، 0030 قفل sync شیت، …)
│   ├── scripts/seed_demo.py  # دادهٔ نمایشی
│   └── tests/
├── frontend/                 # SPA (React + Vite + React Query)
│   └── src/
│       ├── pages/            # صفحات هسته (شامل Settings با کارت تلگرام و TOTP)
│       ├── requests/         # درخواست‌ها و پروژه‌ها
│       ├── perf/             # پرفورمنس: کمپین، پیامک، سوشال، هزینه، شیت، اتصالات
│       ├── components/ui/    # کامپوننت‌های مشترک UI (Card، Toast، EmptyState، …)
│       ├── lib/              # access.ts، focus.ts (منو و تمرکز روزانه)، navigation، roles، …
│       ├── calendarApi.ts    # کلاینت تقویم
│       ├── i18n.tsx          # انگلیسی / فارسی
│       └── api.ts            # کلاینت API
└── docker-compose.yml        # Postgres (+pgvector)، Redis
```

---

## ۴. پشتهٔ فنی

| لایه | فناوری |
|------|--------|
| بک‌اند | Python 3.12+، FastAPI، SQLAlchemy async، Alembic |
| دیتابیس | PostgreSQL (تولید/لوکال) یا SQLite (تست و توسعهٔ سبک) |
| فرانت | React 19، TypeScript، Vite، React Router، React Query |
| زبان رابط | دو زبانه EN/FA با RTL برای فارسی (`LocaleProvider`) |
| احراز هویت | JWT + رمز هش‌شده + TOTP اختیاری برای ورود |
| AI | عامل‌های tool-only؛ پلنر rules یا LLM (مثلاً 9Router)؛ Hybrid RAG |
| کانال پرسنل | تلگرام (و اختیاری باله) — polling یا webhook؛ outbox پس‌زمینه |
| تست | pytest (SQLite در حافظه لوکال؛ Postgres در CI)، Vitest، Playwright |

نسخهٔ API فعلی **0.17.0** است (Core + Agents + CRM سبک + LLM planner + Campaigns + کانال تلگرام پرسنل + لایهٔ سازمانی/گزارش‌ها + پرفورمنس مارکتینگ + درخواست، پروژه، هزینهٔ مشترک و گزارش کار).

---

## ۵. مفاهیم دامنه (خلاصه)

### سازمان

سازمان → شعبه → دپارتمان → تیم → کاربر  
هر کاربر نقش (Role)، محدودهٔ داده (Data Scope) و مجوزهای ریز دارد.

### کار و همکاری

- **Work Item**: هاب همکاری؛ شرکت‌کنندگان چندنفره
- **Task**: چند مسئول با نقش (OWNER / ASSIGNEE / REVIEWER / …)، وابستگی، امکان هدف تیمی/شعبه‌ای
- **Delegation**: واگذاری وظیفه با ثبت ممیزی و اعلان
- **Assignment Engine**: پیشنهاد/اعمال مسئول بر اساس نقش، شعبه، بار کاری و روابط سازمانی

### ارتباطات

- گفتگو + پیام روی کانال‌هایی مثل WEB / TELEGRAM / SYSTEM
- لینک اختیاری به: کار مشترک، پیگیری، خودرو، مشتری، **موضوع گفتگو** (`campaigns`)
- کانال تلگرام برای پرسنل: اتصال حساب، اعلان، اقدام با دکمه، دستورهای کوتاه، پرسش آزاد (RAG)

### موجودی

خودرو با وضعیت (موجود، رزرو، فروخته‌شده، …)، تاریخچه، درخواست شعبه.

### CRM سبک

مشتری (نام، تلفن، ایمیل، یادداشت) قابل اتصال به کار و پیگیری.

### موضوع گفتگو (ارتباطات — `campaigns`)

موجودیت بازاریابی هسته با وضعیت (DRAFT / ACTIVE / PAUSED / …).  
در صفحهٔ **پیام‌ها** لیست می‌شود؛ گفتگوها را می‌توان فیلتر و به **موضوع گفتگو** وصل کرد. این با **کمپین پرفورمنس** (`pm_campaign`) یکی نیست — واژه‌نامه: [`vocabulary.md`](vocabulary.md).

### درخواست کار و پروژه

کار سازمانی که از مدیر به یک تیم می‌رود و آنجا به اجرا تبدیل می‌شود. ماژول جداست (`backend/app/requests`، جدول‌های `work_request` و `work_project`) و زیر پرفورمنس نیست.

- **درخواست** (REQ-NNN): عنوان، نوع (تبلیغات / قیمت و پست‌ها / عمومی)، اولویت (کم / معمولی / بالا)، مهلت، تیم مقصد. تیم مقصد فقط تیم اصلی است؛ زیرمجموعه‌ها اینجا انتخاب نمی‌شوند. وضعیت: `new` ← `in_review` ← `converted` ← `done`، یا `rejected`.
- **پروژه** (PRJ-NNN): یک درخواست به یک یا چند پروژه تبدیل می‌شود. پروژه تیم‌محور است (نه شخص‌محور) و نوعش را تیم تریاژ تعیین می‌کند: پرفورمنس، تولید محتوا، فیلم‌برداری، طراحی، عمومی. وضعیت: `new` ← `in_progress` ← `done`.
- با ساخت اولین پروژه، وضعیت درخواست خودکار `converted` می‌شود. درخواست‌دهنده پروژه را **فقط‌خواندنی** باز می‌کند (خلاصه، کمپین‌ها، لینک گزارش)؛ ساخت پروژه برای او ← ۴۰۳.
- گفتگوی کمپین پرفورمنس با `POST /perf/campaigns/{id}/thread` به spine درخواست/پروژه وصل می‌شود.
- تریاژ می‌تواند به‌جای پروژه، درخواست را مستقیم به وظیفه تبدیل کند (مناسب «قیمت و پست‌ها»). صفحهٔ `/projects/:id` تب‌های نمای کلی، وظایف، لینک، گفتگو، هزینه، فعالیت و پنل نوع دارد. قالب وظایف فقط با دکمهٔ «اعمال قالب» ساخته می‌شود.
- هزینهٔ وصل‌شده به پروژه یا درخواست اول تأیید سرپرست تیم (`manager`) می‌خواهد، بعد مالی. `GET /reports/work` محدوده را به نقش محدود می‌کند. جزئیات در `docs/unification-plan.md`.

### پرفورمنس مارکتینگ

اجرای تبلیغات (`backend/app/perf`). کمپین پرفورمنس (`pm_campaign`، کدهایی مثل S94) با `project_id` به پروژه وصل می‌شود. وضعیت: `draft` / `active` / `done`.

شاخه‌های موازی هر کمپین، که صف «گام بعدی» اولین شکافش را نشان می‌دهد:

- بودجه و ماشین‌ها ← چیدن پیج و استوری (`planned` ← `published`) ← اینسایت
- پیامک: متن، چک قوانین، لیست گیرنده، لیست سیاه، ثبت ارسال (`new` ← `planned` ← `done`)، فایل تحویل
- هزینه: `requested` ← (اگر به پروژه/درخواست وصل است) `manager_ok` با دکمهٔ «تأیید سرپرست تیم» ← `expense.pay` → `paid` + `recorded`، یا `rejected`. همان شخص سرپرست و مالی نمی‌شود. `seen_amount_toman`؛ درخواست‌دهنده تأیید نمی‌کند.
- بریف کمپین (پیش‌نویس با مدل زبانی، ویرایش انسانی)
- خواندن میزیتو (فقط‌خواندنی): کارت‌ها و درخواست‌های تبلیغ؛ هیچ نوشتنی در میزیتو نیست
- شیت گوگل: شیت‌های منبع فقط append؛ شیت گزارش پنل بازنویسی با دکمه/API. فهرست کمپین `push=False`؛ نوشتن واقعی با قفل `perf_sync_state` (۴۰۹ هم‌زمانی). جزئیات: [`performance-flowchart.html`](performance-flowchart.html).

### تقویم محتوا و کار

ماژول `backend/app/calendar` — API و UI `/calendar` **فقط `org.admin`** (`canSeeCalendar` در `access.ts`). ردیف دستی ماه جلالی، رویداد از کار و مارکتینگ، لایه‌های long/mid/short/reactive؛ seed آبان ۱۴۰۵ در `calendar/seed.py`.

### تیم‌های زیرمجموعه

تیم‌ها `parent_team_id` دارند. **MKT_T** والد **MKT_PERF**، **MKT_DESIGN**، **MKT_FILM** است؛ **MKT_CONTENT** در طرح سازمان است ولی در seed دمو فعلاً ساخته نمی‌شود. زیرتیم‌ها با `team_home_team_id` خانهٔ والد را می‌بینند (`/teams/{id}`). فروش (**SALES_T**) و مالی (**FIN_T**) تیم‌های اصلی جدا هستند.

### دانشنامه

اسناد سیاست/SOP → تکه‌بندی → امبدینگ → جستجو برای انسان و AI (و پاسخ‌های بات تلگرام).

### اعلان و SLA

اعلان برای تخصیص و رویدادها؛ سیاست SLA بر اساس اولویت با حالت‌های هشدار و نقض.  
اعلان‌های تلگرام از طریق **outbox** ارسال می‌شوند (retry، 429/403، ترجیحات و ساعات سکوت).

جزئیات بیشتر: [`domain-model.md`](domain-model.md)، [`collaboration.md`](collaboration.md)، [`communication.md`](communication.md).

---

## ۶. کانال تلگرام پرسنل

تلگرام **لبه** است، نه منبع حقیقت. همهٔ پیام‌ها و اقدامات از سرویس‌های دامنه عبور می‌کنند و در SQL ذخیره می‌شوند.

### قابلیت‌های پیاده‌شده

| قابلیت | توضیح |
|--------|--------|
| اتصال حساب | کارت «تلگرام» در تنظیمات؛ کد لینک با انقضا؛ deep link به بات |
| حالت اجرا | `TELEGRAM_MODE`: `off` / `polling` / `webhook` |
| ورود پیام | dedupe با `update_id`؛ DM پایدار؛ پیام‌های فارسی |
| اعلان | صف outbox + دیسپچر پس‌زمینه؛ ترجیحات نوع اعلان و quiet hours |
| اقدام سریع | دکمه‌های callback (انجام / باز / واگذاری) با امضای امن |
| دستورها | مثلاً `/kar`، `/payam`، `/khodro`؛ تأیید قبل از ساخت کار مشترک |
| دستیار | متن آزاد → Hybrid RAG با محدودیت نرخ |
| زمان‌بندی | بررسی SLA و digest صبحگاهی با قفل ضد اجرای دوبل |
| باله (اختیاری) | همان مدل با `provider` روی حساب و `BALE_*` |

### تنظیم محلی

در `.env` (هرگز توکن را commit نکنید):

```env
TELEGRAM_MODE=polling
TELEGRAM_BOT_TOKEN=
TELEGRAM_BOT_USERNAME=
TELEGRAM_LINK_CODE_TTL_MINUTES=10
WEB_APP_BASE_URL=http://localhost:5173
```

جزئیات بیشتر: [`communication.md`](communication.md) و کد در `backend/app/integrations/telegram/`.

---

## ۷. رابط کاربری — معماری اطلاعات

منو بر اساس هدف کاربر است؛ **حداکثر شش مقصد روزانه** با `frontend/src/lib/focus.ts` و فیلتر مسیرها با `lib/access.ts` (`canSeeNavPath`). درخواست‌ها در گروه اصلی؛ مارکتینگ اجرا + «خانه مارکتینگ» (`/teams/{teamId}`) برای نقش‌های مرتبط. `/approvals` به `/my-work` می‌رود؛ `/cases` به خانه. اتصالات پرفورمنس و تنظیمات **پایین** منو:

| منو | مسیر | کار |
|-----|------|-----|
| خانه | `/` | تمرکز روزانه، KPI نقش‌محور |
| کارهای من | `/my-work` | وظایف، work item، پرونده؛ تأیید قیمت/هزینه |
| درخواست‌ها | `/requests` | ثبت، تریاژ، تبدیل به پروژه (`request.*`) |
| پروژه‌ها | `/projects` | PRJ-…؛ مدیر فقط‌خواندنی؛ پرفورمنس منو ندارد |
| تقویم | `/calendar` | فقط ادمین سایت (`org.admin`) |
| قیمت و پست‌ها | `/pricing` | تابلوی قیمت و پست (مدیر و مارکتینگ؛ نه مالی خام) |
| پیام‌ها | `/communication` | گفتگو (`conversation.read`) |
| خودروها | `/vehicles` | انبار (`inventory.read`) |
| مشتریان | `/customers` | فقط ادمین |
| دستیار | `/agent` | عامل با مجوز (در منوی کناری نیست؛ مسیر مستقیم) |
| خانه مارکتینگ | `/teams/{id}` | وضعیت کلی MKT_T برای سرپرست/پرفورمنس/اعضا |
| مارکتینگ ← پرفورمنس … | `/perf`، `/perf/campaigns`، … | سرپرست مارکتینگ: کمپین + شیت؛ پرفورمنس: اجرا؛ مالی (`finance`): فقط `/perf/money` |
| همکاران / قوانین | `/people`، `/knowledge` | `user.read` / `kb.read` (در قالب‌های اصلی از `SHARED_READ`) |
| گزارش‌ها | `/reports` | همهٔ نقش‌ها (دامنهٔ داده متفاوت) |
| مدیریت | `/admin` | `org.admin` |
| اتصالات / تنظیمات | `/perf/connections`، `/settings` | یکپارچه‌سازی پرفورمنس؛ سازمان، تلگرام، TOTP |
| اعلان‌ها | `/notifications` | فید اعلان |

### تجربه همکاری (نه فقط مدیریت کار)

کاربر نباید اول با واژه‌های Work Item / Case روبه‌رو شود. باید ببیند:

```text
ارتباط → همکاری → مسئولیت → اقدام بعدی
```

مثال خانه:

```text
فروش Camry 2024
رضا → پیگیری پرونده
سارا → آماده‌سازی آگهی
مهلت: ۱۶:۰۰
```

با کلیک، صفحهٔ هدف مشترک افراد درگیر، اقدام‌ها، گفتگو و «قدم بعدی» را نشان می‌دهد.

جزئیات UX: [`information-architecture.md`](information-architecture.md)، [`user-flows.md`](user-flows.md).

---

## ۸. دستیارهای هوشمند (Agents)

همهٔ عامل‌ها **فقط از طریق ابزارهای دارای مجوز** عمل می‌کنند؛ مثل کاربر محدود به RBAC هستند و موجودیت ساختگی نمی‌سازند.

| حالت در UI | Endpoint | کاربرد |
|------------|----------|--------|
| ارتباطات | `POST /agent/communication` | ساخت کار مشترک و وظیفه از متن آزاد |
| موجودی | `POST /agent/inventory` | فرصت از ماندگی انبار / تقاضای شعبه |
| فروش | `POST /agent/sales` | پیگیری‌های کهنه و pipeline |
| خرید | `POST /agent/purchase` | تقاضای خرید / فروشنده |
| دیوار | `POST /agent/divar` | آماده‌سازی آگهی (ثبت نهایی دستی) |

پلنر پیش‌فرض: `rules` (قطعی). با تنظیم `LLM_PROVIDER` می‌توان LLM گرفت؛ در خطا به rules برمی‌گردد.

Hybrid RAG (`/rag` و مسیر پرسش آزاد بات): پاسخ از SQL ساخت‌یافته + بازیابی برداری دانشنامه، با منبع.

---

## ۹. امنیت و مجوزها

مجوزها متمرکز در `backend/app/core/permissions.py` هستند. قالب‌های `requester` / `lead` / `member` با `SHARED_READ` (`user.read`، `kb.read`)؛ نقش‌های تخصصی مارکتینگ (`marketing_manager`، `performance_marketing`، `designer`، `filmmaker`) جدا از seed تعریف می‌شوند. UI: `frontend/src/lib/access.ts`. نمونهٔ کدها:

- `conversation.read/write`
- `work_item.*`، `task.*` (شامل `task.assign`، `task.delegate`)
- `inventory.*`، `customer.*`، `campaign.*`
- `request.create` / `request.triage` / `request.manage` — ساخت درخواست، تریاژ و تبدیل به پروژه، دیدن همه
- `perf.read` / `perf.write` / `perf.approve` — دیدن و اجرای پرفورمنس
- `price.approve` / `expense.pay` — تأیید قیمت و پست‌ها جدا از پرداخت هزینه (`finance_perms.py`؛ حذف alias `price.write`: [`adr/005-price-write-sunset.md`](adr/005-price-write-sunset.md))
- `expense.approve` / `request.triage` — گام `manager_ok` روی هزینهٔ وصل به پروژه/درخواست
- `kb.*`، `agent.run`، `search.run`، …

نقش `org.admin` همهٔ چک‌ها را دور می‌زند.  
محدودهٔ داده (سازمان / شعبه / تیم / خود) روی نقش ذخیره می‌شود؛ اعمال سخت اسکوپ سازمانی روی همهٔ مسیرهای دارای شناسه انجام شده و با `tests/test_idor_scope.py` (۲۷ تست) گارد خورده است: delegate/assign وظیفه، تکمیل و SLA وظیفه و پرونده، وابستگی‌ها، شرکت‌کنندگان، پیام‌های گفتگو، پیشرفت کار، اعضای تیم و روابط سازمانی، تغییر وضعیت و اتصال شعبهٔ خودرو، افزودن مهارت.

ورود دو مرحله‌ای با **TOTP** اختیاری است: کارت فعال‌سازی با QR در تنظیمات و فیلد کد در صفحهٔ ورود.  
توکن بات تلگرام فقط در `.env`؛ در لاگ‌ها ماسک می‌شود. callback دکمه‌ها امضا دارند تا دستکاری نشوند.

خروجی‌های تلگرام: تراکنش نوشتن حین فراخوانی‌های شبکه باز نمی‌ماند (commit per-row در `dispatch_pending` — هم در runtime و هم در job ورکر)؛ خطاهای 4xx غیر از 429 دائمی‌اند و retry نمی‌شوند؛ دکمه‌های URL غیر-https هنگام enqueue حذف می‌شوند تا ردیف سمی ساخته نشود.

هم‌زمانی SQLite: درخواست‌های API با **BEGIN IMMEDIATE** شروع می‌شوند (deadlock ارتقای قفلِ read-then-write حذف می‌شود و نویسنده‌ها با busy_timeout صف می‌شوند) و حلقه‌های worker روی انجین جداگانه‌ای با BEGIN عادی (deferred) کار می‌کنند تا برای خواندن قفل نوشتن نگیرند و API را گرسنه نکنند (`app/db/session.py`: `AsyncSessionLocal` در برابر `WorkerSessionLocal`).

---

## ۱۰. API — ماژول‌های اصلی

روترهای هسته در `backend/app/api/routes/` هستند. پرفورمنس و درخواست‌ها روتر جدا دارند و هر روتر هم روی ریشه و هم زیر `/v1` سوار می‌شود:

| ماژول | موضوع |
|-------|--------|
| `app/requests` | درخواست کار و پروژه: فهرست، ساخت، تریاژ، تبدیل به پروژه |
| `app/perf` | کمپین پرفورمنس، پیامک، سوشال، هزینه، شیت، اتصالات، میزیتو، بریف، thread کمپین |
| `app/calendar` | تقویم محتوا — خواندن/نوشتن با `request.triage` / `perf.write` و اسکوپ تیم؛ اکسل و LLM فقط `org.admin` |
| `pricing` | تابلوی قیمت، اسلات، تأیید، ثبت پست |
| `org` | ورود، bootstrap، کاربران، شعب، تیم‌ها، روابط |
| `work` | کار مشترک، وظیفه، پیگیری، گفتگو، اعلان، SLA |
| `inventory` | خودرو و درخواست موجودی |
| `customers` | CRM |
| `campaigns` | موضوع گفتگو / ارتباطات (جدا از `pm_campaign` پرفورمنس) |
| `knowledge` | آپلود و جستجوی دانش |
| `agent` | عامل‌های AI |
| `assignment` | پیشنهاد تخصیص |
| `search` / `rag` | جستجو و Hybrid RAG |
| `telegram` | وضعیت، لینک/قطع، ترجیحات، webhook، setup، باله |
| `enterprise` | ممیزی و خروجی آن، تأیید چندمرحله‌ای، KPI و خروجی‌ها (CSV/Excel/PDF)، نمای کلی ادمین، نگهداشت داده |

مستندات تعاملی: http://localhost:8000/docs (اگر API روی پورت دیگری است همان را جایگزین کنید).

---

## ۱۱. اجرای محلی

```bash
# ریشهٔ پروژه
cp .env.example .env
# برای تلگرام لوکال: TELEGRAM_MODE=polling و توکن/یوزرنیم بات را پر کنید

# اختیاری: زیرساخت
docker compose up -d postgres redis

# API — پورت پیش‌فرض 8000
cd backend
uv sync --extra dev
uv run alembic upgrade head          # اگر Postgres
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# دادهٔ نمایشی (idempotent)
uv run python -m scripts.seed_demo

# فرانت — پورت 5173 (پروکسی /api → بک‌اند؛ هدف در vite.config.ts)
cd frontend
npm install
npm run dev
```

| سرویس | آدرس |
|-------|------|
| وب | http://localhost:5173 |
| API | http://localhost:8000 |
| Health | http://localhost:8000/health |
| OpenAPI | http://localhost:8000/docs |

اگر پورت API را عوض کردید، `frontend/vite.config.ts` → `server.proxy["/api"].target` را هم‌تراز کنید.

ورود دمو: سازمان `autoco`، ایمیل `ali@autoco.example`، رمز `password`.

تست بک‌اند (Postgres — [`adr/004-sqlite-retirement.md`](adr/004-sqlite-retirement.md)):

```bash
cd backend
uv run pytest -q
```

---

## ۱۲. جریان‌های نمونهٔ کاربر

1. **مدیر از خانه** موارد نیازمند توجه را می‌بیند → کارهای من / کار مشترک را باز می‌کند.
2. **درخواست کار:** مدیر در «درخواست‌ها» برای تیم مارکتینگ (یا مالی) درخواست می‌سازد. مارکتینگ تریاژ می‌کند و یک یا چند پروژه با تیم مجری (پرفورمنس، تولید محتوا، فیلم‌برداری، طراحی) می‌سازد. کمپین پرفورمنس به پروژه وصل می‌شود. مدیر روی همان کارت می‌بیند برای درخواستش چه پروژه‌هایی تعریف شده؛ هر نقش فقط گزارش خودش را می‌بیند.
3. **فروش و بازاریابی روی یک خودرو** کار مشترک دارند؛ وظایف جدا با مهلت و اعلان.
4. **در پیام‌ها** دربارهٔ موضوع گفتگو (مثلاً Tucson) حرف می‌زنند؛ موضوع را از لیست انتخاب می‌کنند تا گفتگوها فیلتر شود؛ اگر گفتگو نیاز به پاسخ داشته باشد در «نیاز به پاسخ» می‌آید.
5. **دستیار** با جملهٔ فارسی کار و وظیفه می‌سازد (با تأیید ابزارها).
6. **موجودی** خودرو را باز می‌کند و از همان‌جا به کار مشترک یا پیگیری می‌رود.
7. **پرونده‌ها:** وضعیت و مسؤول از همان صفحه تغییر می‌کند و در تایم‌لاین ثبت و اعلان می‌شود.
8. **تلگرام پرسنل:** تنظیمات → اتصال بات → دریافت اعلان وظیفه روی موبایل → انجام با دکمه یا دستور کوتاه؛ پرسش آزاد از دانش/وضعیت خودرو.

جزئیات: [`user-flows.md`](user-flows.md).

متن ارائهٔ شفاهی: [`presentation-fa.txt`](presentation-fa.txt).

---

## ۱۳. نقشهٔ مستندات تخصصی

| فایل | موضوع |
|------|--------|
| [`architecture.md`](architecture.md) | لایه‌بندی سیستم |
| [`domain-model.md`](domain-model.md) | مدل دامنه |
| [`collaboration.md`](collaboration.md) | هستهٔ همکاری |
| [`communication.md`](communication.md) | کانال‌ها و تلگرام |
| [`crm.md`](crm.md) | مشتریان |
| [`knowledge-base.md`](knowledge-base.md) | دانشنامه |
| [`hybrid-rag.md`](hybrid-rag.md) | Hybrid RAG |
| [`llm-planner.md`](llm-planner.md) | پلنر LLM |
| [`inventory-agent.md`](inventory-agent.md) / [`sales-agent.md`](sales-agent.md) / [`purchase-agent.md`](purchase-agent.md) / [`divar-agent.md`](divar-agent.md) | عامل‌های تخصصی |
| [`web-app.md`](web-app.md) | اپ وب |
| [`information-architecture.md`](information-architecture.md) | ناوبری و مسیرها |
| [`ux-principles.md`](ux-principles.md) / [`ux-audit.md`](ux-audit.md) | اصول و ممیزی UX |
| [`development-roadmap.md`](development-roadmap.md) | نقشهٔ فازها |
| [`presentation-fa.txt`](presentation-fa.txt) | متن ارائهٔ فارسی |
| [`cm-flowchart.html`](cm-flowchart.html) | فلوچارت تفصیلی کل سامانه (وضعیت‌ها، شاخه‌ها، دسترسی‌ها، تقویم) |
| [`performance-flowchart.html`](performance-flowchart.html) | فلوچارت تفصیلی پرفورمنس |
| [`team-tree.html`](team-tree.html) | درخت تیم و حساب‌های دمو AutoCo |
| [`roles-plan.md`](roles-plan.md) | قالب نقش‌ها و دسترسی صفحات |

---

## ۱۴. اصول طراحی محصول (خلاصه)

- از **سیستم مدیریت کار** به **سیستم مدیریت همکاری** فکر کنید: افراد ↔ تیم ↔ گفتگو ↔ هدف مشترک ↔ اقدام ↔ نتیجه
- واژگان کاربرمحور در UI؛ اصطلاحات فنی فقط در API/docs
- خانه = «الان چه خبر است؟» نه داشبورد موجودیت‌ها
- ارتباطات = اینباکس سازمانی (نیاز به پاسخ، کار مشترک، شعبه، کمپین) نه فقط لیست چت
- یک کار در هر بخش صفحه؛ حالت خالی و خطای خوانا
- AI کمکی است، نه جایگزین مالکیت انسان
- کانال بیرونی (تلگرام / دیوار / میزیتو) جایگزین سیستم نیست — فقط لبه است؛ میزیتو فقط خوانده می‌شود
- درخواست مال سازمان است و به تیم اصلی می‌رود؛ شکستن کار به زیرتیم‌ها در پروژه‌سازی انجام می‌شود
- تغییر ظاهر از `components/ui` تا کل اپ یکدست بماند
- ریتم عمودی واحد: یک مالک فاصله (کانتینر صفحه)، بدون استایل‌های درون‌خطی؛ گارد Playwright ریتم را تست می‌کند

---

## ۱۵. وضعیت فعلی و جهت بعدی

**پیاده‌شده (نمای کلی):** سازمان و RBAC (`access.ts` / `focus.ts` / `permissions.ts`)، کار و گفتگو، CRM (منوی مشتریان فقط `org.admin`؛ فروشنده با `case.read` پرونده می‌بیند نه CRM عمومی)، موضوع گفتگو، RAG و عامل‌ها، تلگرام، ادمین و TOTP. **تقویم** با اسکوپ تیم برای سرپرست/پرفورمنس (`request.triage` / `perf.write`). پرفورمنس: کد کمپین در DB (`PmCampaignSequence`)، thread، هزینه با `manager_ok` + ممیزی `payment.*` + `expense.pay`، شیت با `perf_sync_state` و idempotency export. رمزنگاری فیلد (شبا، میزیتو، پنل): [`adr/003-field-encryption.md`](adr/003-field-encryption.md). درخواست/پروژه، spine، دید درخواست‌دهنده فقط‌خواندنی. ADRها: SQLite retirement، sunset `price.write`. مستندات: `cm-flowchart.html`، `performance-flowchart.html`، `team-tree.html`.

خطوط قرمز پرفورمنس و درخواست: پرداخت، ارسال واقعی پیامک، نوشتن در میزیتو، ساخت کمپین، تبدیل درخواست به پروژه و تأیید قیمت خودکار نمی‌شوند.

**باقی‌مانده / جهت بعدی:** حذف کامل fallback `price.write` پس از تاریخ ADR 005؛ مهاجرت دادهٔ تولید به Postgres طبق ADR 004؛ آداپتر واقعی پیامک/ایمیل/ERP؛ observability کامل در `docker-compose.prod.yml` (nginx، Prometheus، Grafana، Loki). refresh در کوکی **httpOnly** و قفل ورود و seed guard در کد هستند — [`security-and-audit.md`](security-and-audit.md). جزئیات پشتیبان: [`runbooks/backup.md`](runbooks/backup.md).

**بودجه در برابر هزینه:** گزارش کمپین پرفورمنس (`/perf/campaigns/{id}`) بودجهٔ برنامه‌ای را با هزینهٔ ثبت‌شده مقایسه می‌کند؛ هزینهٔ وصل به پروژه/درخواست قبل از مالی گام `manager_ok` می‌خواهد (`expense.approve` / `request.triage`).

---

*این سند نمای کلی محصول است. برای جزئیات پیاده‌سازی به فایل‌های تخصصی بالا و کد در `backend/` و `frontend/` مراجعه کنید.*
