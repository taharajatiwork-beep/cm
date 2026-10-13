import { describe, expect, it } from "vitest";

import { focusRoleFromCode, roleTitle } from "./roles";

describe("focusRoleFromCode", () => {
  it("maps database role codes, not inventory permissions", () => {
    expect(focusRoleFromCode("requester")).toBe("manager");
    expect(focusRoleFromCode("lead")).toBe("manager");
    expect(focusRoleFromCode("member")).toBe("viewer");
    expect(focusRoleFromCode("seller")).toBe("seller");
    expect(focusRoleFromCode("marketing_manager")).toBe("marketing");
  });
});

describe("roleTitle", () => {
  it("matches the demo accounts", () => {
    expect(roleTitle("admin")).toBe("ادمین سایت");
    expect(roleTitle("requester", "شعبهٔ تهران")).toBe("مدیر");
    expect(roleTitle("requester", "شعبهٔ مشهد")).toBe("مدیر شعبه مشهد");
    expect(roleTitle("member")).toBe("عضو");
    expect(roleTitle("marketing_manager")).toBe("سرپرست مارکتینگ");
    expect(roleTitle("performance_marketing")).toBe("پرفورمنس مارکتینگ");
    expect(roleTitle("lead")).toBe("سرپرست");
    expect(roleTitle("viewer")).toBe("بازدیدکننده");
  });
});
