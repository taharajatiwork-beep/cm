import { describe, expect, it } from "vitest";
import { liveConnectionsQuery, savedConnectionsQuery } from "./connectionsQuery";

describe("connection status queries", () => {
  it("never runs the live check on its own", () => {
    expect(liveConnectionsQuery.enabled).toBe(false);
    expect(liveConnectionsQuery.retry).toBe(false);
    expect("refetchInterval" in liveConnectionsQuery).toBe(false);
    expect(liveConnectionsQuery.refetchOnMount).toBe(false);
    expect(liveConnectionsQuery.refetchOnWindowFocus).toBe(false);
    expect(liveConnectionsQuery.refetchOnReconnect).toBe(false);
  });

  it("keeps saved and live status under separate keys", () => {
    expect(savedConnectionsQuery.queryKey).toEqual(["perf", "connections", "saved"]);
    expect(liveConnectionsQuery.queryKey).toEqual(["perf", "connections", "live"]);
    expect("refetchInterval" in savedConnectionsQuery).toBe(false);
  });
});
