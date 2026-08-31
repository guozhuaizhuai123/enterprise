import { formatAccountRoleLabel } from "./accountFormat.ts";

function assertEqual(actual: unknown, expected: unknown): void {
  if (actual !== expected) throw new Error(`Expected ${expected}, got ${actual}`);
}

assertEqual(formatAccountRoleLabel("employee", ["employee", "finance", "manager"]), "财务复核 / 部门负责人");
assertEqual(formatAccountRoleLabel("employee", ["employee"]), "员工");
assertEqual(formatAccountRoleLabel("admin", ["admin"]), "管理员");
