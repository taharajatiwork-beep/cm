import type { ReactNode } from "react";
import { Bi } from "../../i18n";
import { symbolUrl } from "../../brand/logos";

export function ForbiddenState({
  titleEn = "You don’t have access to this section",
  titleFa = "به این بخش دسترسی ندارید",
  bodyEn = "Your role can’t open this page. If you think you need it, ask your system admin.",
  bodyFa = "نقش شما اجازهٔ دیدن این بخش را ندارد. اگر فکر می‌کنید باید ببینید، با مدیر سیستم هماهنگ کنید.",
  action,
  className = "",
}: {
  titleEn?: string;
  titleFa?: string;
  bodyEn?: string;
  bodyFa?: string;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={`empty-state ui-empty ${className}`.trim()}>
      <img className="empty-state-mark" src={symbolUrl} alt="" width={48} height={34} />
      <h3>
        <Bi en={titleEn} fa={titleFa} />
      </h3>
      <p>
        <Bi en={bodyEn} fa={bodyFa} />
      </p>
      {action}
    </div>
  );
}
