import {
  canEditOwnedDocument,
  formatOwnerLabel,
  getDepartmentHref,
  getEmployeeMembershipLabels,
  overviewAssistantHref,
  primaryAdminRoutes,
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

// 管理端一级入口只有两个：管理助手与企业全景，其余页面保留为深链
assertEqual(primaryAdminRoutes(), [
  { to: "/admin/assistant", label: "管理助手" },
  { to: "/admin/overview", label: "企业全景" },
]);

assertEqual(
  overviewAssistantHref("查看本月费用", "dept/a"),
  "/admin/assistant?prompt=%E6%9F%A5%E7%9C%8B%E6%9C%AC%E6%9C%88%E8%B4%B9%E7%94%A8&department=dept%2Fa",
);
assertEqual(overviewAssistantHref("查看本月费用"), "/admin/assistant?prompt=%E6%9F%A5%E7%9C%8B%E6%9C%AC%E6%9C%88%E8%B4%B9%E7%94%A8");
assertEqual(overviewAssistantHref("查看本月费用", ""), "/admin/assistant?prompt=%E6%9F%A5%E7%9C%8B%E6%9C%AC%E6%9C%88%E8%B4%B9%E7%94%A8");
