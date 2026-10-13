/** Deep links for in-app notifications. */
export function notificationHref(entityType: string | null | undefined, entityId: string | null | undefined): string | null {
  if (!entityType || !entityId) return null;
  if (entityType === "task") return `/my-work?task=${entityId}`;
  if (entityType === "project" || entityType === "work_project") return `/projects/${entityId}`;
  if (entityType === "request" || entityType === "work_request") return `/requests/${entityId}`;
  if (entityType === "conversation") return `/communication?c=${entityId}`;
  return null;
}
