export const PROJECT_STATUS_LABEL: Record<string, string> = {
  new: "تازه",
  in_progress: "در جریان",
  done: "تمام",
};

export const STATUS_TONE: Record<string, "ok" | "warn" | "danger"> = {
  new: "warn",
  in_progress: "warn",
  done: "ok",
};

export const CM_STATUS_COLUMNS = [
  { key: "new", label: "تازه" },
  { key: "in_progress", label: "در جریان" },
  { key: "done", label: "تمام" },
] as const;

export const LIST_PAGE_SIZE = 50;
