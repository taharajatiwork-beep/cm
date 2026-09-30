/**
 * One place for every TanStack Query key.
 *
 * The first element is always the resource path and the rest is the filter,
 * so `invalidateQueries({ queryKey: queryKeys.customersRoot })` re-runs every
 * filtered variant of that resource without touching anything else.
 */

export const queryKeys = {
  peopleRoot: ["people"] as const,
  people: (q: string) => ["people", q] as const,
  personDetail: (id: string) => ["people", id, "detail"] as const,

  customersRoot: ["customers"] as const,
  customers: (q: string) => ["customers", q] as const,

  vehiclesRoot: ["vehicles"] as const,
  vehicles: (q: string, canRead: boolean) => ["vehicles", q, canRead] as const,
  vehicleContext: (id: string) => ["vehicles", "context", id] as const,

  workItemsRoot: ["work-items"] as const,
  workItems: (canRead: boolean) => ["work-items", canRead] as const,
  workItemDetail: (id: string) => ["work-items", id, "detail"] as const,

  notifications: ["notifications"] as const,
  communicationRoot: ["communication-board"] as const,
  communication: (userId: string | undefined, archived: boolean) =>
    ["communication-board", userId, archived] as const,
  conversationMessages: (id: string) => ["communication-messages", id] as const,

  branches: ["branches"] as const,
  teams: ["teams"] as const,
  teamMembers: (id: string) => ["teams", id, "members"] as const,
  departments: ["departments"] as const,
  knowledge: ["knowledge"] as const,

  telegramStatus: ["telegram", "status"] as const,
};

/** True when `key` is the root or a filtered variant of that root. */
export function isUnder(key: readonly unknown[], root: readonly unknown[]): boolean {
  if (root.length > key.length) return false;
  return root.every((part, i) => part === key[i]);
}
