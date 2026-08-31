import {
  formatEmployeeDisplayName,
  formatEmploymentStatus,
  formatOrgMemberships,
} from "./organizationFormat.ts";

function assertEqual(actual: unknown, expected: unknown): void {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(`Expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}

assertEqual(formatEmploymentStatus("probation"), "试用期");
assertEqual(formatEmploymentStatus("active"), "在职");
assertEqual(formatEmploymentStatus("suspended"), "停职");
assertEqual(formatEmploymentStatus("terminated"), "已离职");
assertEqual(formatEmploymentStatus("unknown"), "未知状态");

assertEqual(
  formatOrgMemberships([
    { department_id: "d1", department_name: "研发部", position: "工程师", is_primary: true, joined_at: null, left_at: null },
    { department_id: "d2", department_name: "产品部", position: "", is_primary: false, joined_at: null, left_at: null },
  ]),
  ["研发部 · 工程师（主部门）", "产品部"],
);

assertEqual(
  formatEmployeeDisplayName({ username: "alice", full_name: "艾丽丝", status: "active" }),
  "艾丽丝",
);
assertEqual(
  formatEmployeeDisplayName({ username: "alice", full_name: "", status: "terminated" }),
  "alice（已离职）",
);
