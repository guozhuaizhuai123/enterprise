import {
  canEditOwnedDocument,
  formatOwnerLabel,
  getDepartmentHref,
  getEmployeeMembershipLabels,
} from "./adminNavigation.ts";

function assertEqual(actual: unknown, expected: unknown): void {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(`Expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}

assertEqual(getDepartmentHref("dept/one"), "/admin/departments/dept%2Fone");
assertEqual(
  getEmployeeMembershipLabels({
    departments: [
      { id: "a", name: "销售", position: "客户经理", access_level: "member" },
      { id: "b", name: "人事", position: "", access_level: "member" },
    ],
  }),
  ["销售 · 客户经理", "人事"],
);
assertEqual(getEmployeeMembershipLabels({ departments: undefined as never }), []);
assertEqual(formatOwnerLabel("alice", true), "alice");
assertEqual(formatOwnerLabel("alice", false), "alice（已离职）");
assertEqual(canEditOwnedDocument("user-1", "user-1"), true);
assertEqual(canEditOwnedDocument("user-2", "user-1"), false);
