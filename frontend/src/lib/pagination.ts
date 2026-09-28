export function nextCursor(page: { next_cursor: string | null } | undefined): string | undefined {
  return page?.next_cursor ?? undefined;
}
