/** Deep links for in-app notifications. */
export function notificationHref(entityType: string | null | undefined, entityId: string | null | undefined): string | null {
  if (!entityType || !entityId) return null;
  const type = entityType.toLowerCase();
  if (type === "task") return `/my-work?task=${entityId}`;
  if (type === "project" || type === "work_project") return `/projects/${entityId}`;
  if (type === "request" || type === "work_request") return `/requests/${entityId}`;
  if (type === "conversation" || type === "message") return `/communication?c=${entityId}`;
  if (type === "case" || type === "followup" || type === "follow_up") return `/cases?c=${entityId}`;
  if (type === "vehicle") return `/vehicles/${entityId}`;
  if (type === "customer") return `/customers`;
  if (type === "work_item") return `/projects/${entityId}`;
  if (type === "campaign" || type === "pm_campaign") return `/perf/campaigns/${entityId}`;
  return null;
}
