import { buildCompanyStructure } from "./companyStructure.ts";
import type { OrgEmployee, OrgUnit } from "./types/index.ts";

function assertDeepEqual(actual: unknown, expected: unknown): void {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(`Expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}

const units = [
  { id: "finance-dept", name: "财务部门", manager_id: "finance" },
  { id: "hr-dept", name: "人力资源部门", manager_id: "hr" },
] as OrgUnit[];

const employees = [
  { id: "admin", username: "admin", full_name: "总经理", position: "总经理", level: "L5", status: "active", roles: [] },
  { id: "finance", username: "finance", full_name: "财务负责人", position: "财务负责人", level: "L4", status: "active", roles: ["employee", "finance", "manager"] },
  { id: "hr", username: "hr", full_name: "人力资源负责人", position: "人力资源负责人", level: "L4", status: "active", roles: ["employee", "hr", "manager"] },
  { id: "staff", username: "staff", full_name: "法务专员", position: "法务专员", level: "L2", status: "active", roles: ["employee"] },
] as OrgEmployee[];

const structure = buildCompanyStructure(units, employees);

assertDeepEqual(structure.coverage, { filled: 4, total: 4, missing: [] });
assertDeepEqual(structure.levels.map((item) => [item.level, item.people.map((person) => person.username)]), [
  ["L5", ["admin"]],
  ["L4", ["finance", "hr"]],
  ["L2", ["staff"]],
]);

const missingFinance = buildCompanyStructure(
  [{ id: "finance-dept", name: "财务部门", manager_id: null } as OrgUnit],
  [employees[0]],
);
assertDeepEqual(missingFinance.coverage.missing, ["财务复核人", "财务部门负责人", "人力资源角色"]);
