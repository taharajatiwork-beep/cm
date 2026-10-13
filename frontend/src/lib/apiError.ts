import { ApiError } from "../api";

export function isForbiddenError(error: unknown): boolean {
  if (error instanceof ApiError) return error.status === 403;
  const s = String(error instanceof Error ? error.message : error).toLowerCase();
  return (
    s.includes("403") ||
    s.includes("not authorized") ||
    s.includes("missing permission") ||
    s.includes("missing one of permissions")
  );
}
