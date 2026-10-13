/** Normalize FastAPI error bodies (string, {message}, or [{msg}]) for display. */
export function apiErrorDetail(detail: unknown, fallback: string): string {
  if (detail == null || detail === "") return fallback;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) => {
        if (item && typeof item === "object" && "msg" in item) {
          return String((item as { msg: unknown }).msg);
        }
        return "";
      })
      .filter(Boolean);
    if (parts.length) return parts.join(" · ");
  }
  if (typeof detail === "object") {
    const obj = detail as Record<string, unknown>;
    if (typeof obj.message === "string" && obj.message) return obj.message;
  }
  try {
    const encoded = JSON.stringify(detail);
    if (encoded && encoded !== "{}") return encoded;
  } catch {
    /* ignore */
  }
  return fallback;
}
