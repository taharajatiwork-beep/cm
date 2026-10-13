export const REQUEST_STATUS_LABEL: Record<string, string> = {
  new: "جدید",
  in_review: "در بررسی",
  converted: "تبدیل به پروژه",
  rejected: "رد شده",
  done: "انجام شد",
};

export function requestStatusLabel(status: string): string {
  return REQUEST_STATUS_LABEL[status] ?? status;
}
