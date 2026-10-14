/* Provider file intentionally exports hooks and helpers beside its components. */
/* eslint-disable react/only-export-components */
import type { ReactNode } from "react";
import { Bi, useBi } from "./i18n";
import { Badge, Button, Card, EmptyState as UiEmptyState } from "./components/ui";

export { friendlyError } from "./lib/errors";

/** @deprecated Prefer importing EmptyState from components/ui */
export function EmptyState(props: {
  titleEn: string;
  titleFa: string;
  bodyEn: string;
  bodyFa: string;
  action?: ReactNode;
}) {
  return <UiEmptyState {...props} />;
}

/** Human labels for collaboration concepts */
export function concept(en: "shared" | "followup" | "task" | "conversation" | "mywork") {
  const map = {
    shared: { en: "Project", fa: "پروژه" },
    followup: { en: "Follow-up", fa: "پیگیری" },
    task: { en: "Task", fa: "کار" },
    conversation: { en: "Conversation", fa: "گفتگو" },
    mywork: { en: "My Work", fa: "کارهای من" },
  } as const;
  return map[en];
}

export function ConceptHint({ kind }: { kind: "shared" | "followup" | "task" }) {
  const copy = {
    shared: {
      en: "A request starts the chain. A project is where the team does the work. A campaign is only ads and results.",
      fa: "درخواست شروع زنجیره است. پروژه جایی است که تیم کار را انجام می‌دهد. کمپین فقط آگهی و نتیجه است.",
    },
    followup: {
      en: "A request is what a manager asks the team to do. It becomes one or more projects.",
      fa: "درخواست همان چیزی است که مدیر از تیم می‌خواهد. از آن یک یا چند پروژه ساخته می‌شود.",
    },
    task: {
      en: "One concrete action on a project that someone must finish.",
      fa: "یک کار مشخص روی پروژه که یک نفر باید انجام دهد.",
    },
  }[kind];
  return (
    <p className="concept-hint">
      <Bi en={copy.en} fa={copy.fa} />
    </p>
  );
}

export function StatusLabel({ status }: { status: string }) {
  const bi = useBi();
  const map: Record<string, [string, string, string]> = {
    IN_STOCK: ["In stock", "موجود", "ok"],
    RESERVED: ["Reserved", "رزرو", "warn"],
    SOLD: ["Sold", "فروخته‌شده", ""],
    OPEN: ["Not started", "شروع نشده", ""],
    IN_PROGRESS: ["In progress", "در حال انجام", "warn"],
    ASSIGNED: ["To do", "باید انجام شود", ""],
    BLOCKED: ["Waiting on others", "منتظر دیگران", "warn"],
    COMPLETED: ["Done", "انجام شد", "ok"],
    CANCELLED: ["Cancelled", "لغو شده", ""],
    // مقادیر CaseStatus که map قبلی نداشت و خام نمایش داده می‌شد
    WAITING_FOR_RESPONSE: ["Waiting for reply", "در انتظار پاسخ", "warn"],
    WAITING_FOR_USER: ["Waiting on user", "در انتظار کاربر", "danger"],
    PENDING: ["Pending", "در انتظار تأیید", "warn"],
    REJECTED: ["Rejected", "رد شده", "danger"],
    EXPIRED: ["Expired", "منقضی شده", "danger"],
    PENDING_APPROVAL: ["Awaiting approval", "در انتظار تأیید", "warn"],
    FAILED: ["Failed", "ناموفق", "danger"],
    SENT: ["Sent", "ارسال شد", "ok"],
    DRAFT: ["Draft", "پیش‌نویس", ""],
    PUBLISHED: ["Published", "منتشر شد", "ok"],
    SCHEDULED: ["Scheduled", "زمان‌بندی‌شده", "warn"],
    ACTIVE: ["Active", "فعال", ""],
    WARNING: ["Deadline close", "مهلت نزدیک", "warn"],
    NONE: ["No deadline", "بدون مهلت", ""],
    BREACHED: ["Late", "دیر شده", "danger"],
    ESCALATED: ["Sent to manager", "ارجاع به مدیر", "danger"],
    HIGH: ["High", "بالا", "warn"],
    URGENT: ["Urgent", "فوری", "danger"],
    MEDIUM: ["Medium", "متوسط", ""],
    LOW: ["Low", "پایین", ""],
    new: ["New", "جدید", ""],
    in_review: ["In review", "در بررسی", "warn"],
    converted: ["Converted to project", "تبدیل به پروژه", "ok"],
    rejected: ["Rejected", "رد شده", "danger"],
    done: ["Done", "انجام شد", "ok"],
    in_progress: ["In progress", "در جریان", "warn"],
    requested: ["Requested", "درخواست شده", ""],
    approved: ["Approved", "تأیید شده", "ok"],
    paid: ["Paid", "پرداخت شده", "ok"],
    planned: ["Planned", "برنامه‌ریزی‌شده", ""],
  };
  const [en, fa, tone] = map[status] || [status, status, ""];
  return <Badge tone={tone as "" | "ok" | "warn" | "danger"}>{bi(en, fa)}</Badge>;
}

const ONBOARD_KEY = "cm-onboard-v2";

export function highlightNavPath(to: string) {
  window.dispatchEvent(new CustomEvent("cm-nav-highlight", { detail: to }));
}

export function shouldShowOnboarding(): boolean {
  try {
    return localStorage.getItem(ONBOARD_KEY) !== "1";
  } catch {
    return false;
  }
}

export function dismissOnboarding() {
  try {
    localStorage.setItem(ONBOARD_KEY, "1");
  } catch {
    /* ignore */
  }
}

export function recallOnboarding() {
  try {
    localStorage.removeItem(ONBOARD_KEY);
  } catch {
    /* ignore */
  }
}

export function OnboardingBanner({
  titleEn,
  titleFa,
  bodyEn,
  bodyFa,
  steps,
  onDismiss,
}: {
  titleEn: string;
  titleFa: string;
  bodyEn: string;
  bodyFa: string;
  steps: Array<{ labelEn: string; labelFa: string; to: string }>;
  onDismiss: () => void;
}) {
  return (
    <Card className="onboard">
      <div className="onboard-cue">
        <strong>
          <Bi en={titleEn} fa={titleFa} />
        </strong>
        <span>
          <Bi en={bodyEn} fa={bodyFa} />
        </span>
      </div>
      <ol className="onboard-steps">
        {steps.map((step, index) => (
          <li key={step.to}>
            <span className="onboard-step-num">{index + 1}</span>
            <span>
              <Bi en={step.labelEn} fa={step.labelFa} />
            </span>
            <Button
              type="button"
              variant="secondary"
              className="btn-sm"
              onClick={() => highlightNavPath(step.to)}
            >
              <Bi en="Show me" fa="نشانم بده" />
            </Button>
          </li>
        ))}
      </ol>
      <div className="row">
        <Button variant="secondary" onClick={onDismiss}>
          <Bi en="Got it" fa="متوجه شدم" />
        </Button>
      </div>
    </Card>
  );
}
