import type { ReactNode } from "react";
import { Link } from "react-router-dom";
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
    task: { en: "To-do", fa: "کار" },
    conversation: { en: "Conversation", fa: "گفتگو" },
    mywork: { en: "My Work", fa: "کارهای من" },
  } as const;
  return map[en];
}

export function ConceptHint({ kind }: { kind: "shared" | "followup" | "task" }) {
  const copy = {
    shared: {
      en: "A project several people work on together.",
      fa: "پروژه‌ای که چند نفر با هم جلو می‌برند.",
    },
    followup: {
      en: "A specific subject that needs tracking and an owner.",
      fa: "موضوع مشخصی که باید پیگیری شود و مسئول داشته باشد.",
    },
    task: {
      en: "One concrete action someone must finish.",
      fa: "یک کار مشخص که یک نفر باید انجام دهد.",
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
    ACTIVE: ["Active", "فعال", ""],
    WARNING: ["Deadline close", "مهلت نزدیک", "warn"],
    NONE: ["No deadline", "بدون مهلت", ""],
    BREACHED: ["Late", "دیر شده", "danger"],
    ESCALATED: ["Sent to manager", "ارجاع به مدیر", "danger"],
    HIGH: ["High", "بالا", "warn"],
    URGENT: ["Urgent", "فوری", "danger"],
    MEDIUM: ["Medium", "متوسط", ""],
    LOW: ["Low", "پایین", ""],
  };
  const [en, fa, tone] = map[status] || [status, status, ""];
  return <Badge tone={tone as "" | "ok" | "warn" | "danger"}>{bi(en, fa)}</Badge>;
}

const ONBOARD_KEY = "cm-onboard-v1";

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

export function OnboardingBanner({ onDismiss }: { onDismiss: () => void }) {
  return (
    <Card className="onboard">
      <div>
        <strong>
          <Bi en="New here? Three things to know" fa="تازه وارد شده‌اید؟ سه نکته کافی است" />
        </strong>
        <ol className="onboard-steps">
          <li>
            <Link to="/my-work">
              <Bi en="“My Work” lists what you need to do today" fa="«کارهای من» یعنی کارهایی که امروز باید انجام دهید" />
            </Link>
          </li>
          <li>
            <Link to="/communication">
              <Bi en="“Messages” shows who is waiting for your reply" fa="«پیام‌ها» نشان می‌دهد چه کسی منتظر جواب شماست" />
            </Link>
          </li>
          <li>
            <Link to="/agent">
              <Bi en="Not sure? Just ask the assistant in plain words" fa="مطمئن نیستید؟ ساده از دستیار بپرسید" />
            </Link>
          </li>
        </ol>
      </div>
      <Button variant="secondary" onClick={onDismiss}>
        <Bi en="Got it" fa="متوجه شدم" />
      </Button>
    </Card>
  );
}
