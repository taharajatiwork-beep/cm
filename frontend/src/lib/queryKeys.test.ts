import { describe, expect, it } from "vitest";
import { isUnder, queryKeys } from "./queryKeys";

describe("queryKeys", () => {
  it("keeps the resource path first and the filter second", () => {
    expect(queryKeys.customers("ali")).toEqual(["customers", "ali"]);
    expect(queryKeys.people("reza@example.com")).toEqual(["people", "reza@example.com"]);
    expect(queryKeys.vehicles("benz", true)).toEqual(["vehicles", "benz", true]);
  });

  it("scopes detail keys under their resource", () => {
    expect(isUnder(queryKeys.personDetail("u1"), queryKeys.peopleRoot)).toBe(true);
    expect(isUnder(queryKeys.workItemDetail("w1"), queryKeys.workItemsRoot)).toBe(true);
    expect(isUnder(queryKeys.vehicleContext("v1"), queryKeys.vehiclesRoot)).toBe(true);
  });

  it("matches every filtered variant through the root key", () => {
    const roots: Array<[readonly unknown[], readonly unknown[]]> = [
      [queryKeys.customers("ali"), queryKeys.customersRoot],
      [queryKeys.people("reza"), queryKeys.peopleRoot],
      [queryKeys.vehicles("benz", false), queryKeys.vehiclesRoot],
      [queryKeys.workItems(true), queryKeys.workItemsRoot],
    ];
    for (const [key, root] of roots) expect(isUnder(key, root)).toBe(true);
  });

  it("does not leak across resources", () => {
    expect(isUnder(queryKeys.vehicles("benz", true), queryKeys.customersRoot)).toBe(false);
    expect(isUnder(queryKeys.workItemDetail("w1"), queryKeys.peopleRoot)).toBe(false);
    expect(isUnder(["notifications"], queryKeys.teams)).toBe(false);
  });
});
