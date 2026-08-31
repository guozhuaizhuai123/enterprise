import type { OrgEmployee, OrgUnit } from "./types";

const LEVEL_ORDER = ["L5", "L4", "L3", "L2", "L1"];

export interface CompanyStructureLevel {
  level: string;
  label: string;
  people: OrgEmployee[];
}

const LEVEL_LABELS: Record<string, string> = {
  L5: "决策层",
  L4: "管理层",
  L3: "专业骨干",
  L2: "执行层",
  L1: "基础岗位",
};

export function buildCompanyStructure(units: OrgUnit[], employees: OrgEmployee[]) {
  const activePeople = employees.filter((employee) => employee.status === "active");
  const missing: string[] = [];
  const executivePresent = activePeople.some((employee) => employee.level === "L5");
  const financePresent = activePeople.some((employee) => employee.roles.includes("finance"));
  const financeManagerPresent = units.some((unit) => unit.name.includes("财务") && Boolean(unit.manager_id));
  const hrPresent = activePeople.some((employee) => employee.roles.includes("hr"));

  if (!executivePresent) missing.push("决策层负责人");
  if (!financePresent) missing.push("财务复核人");
  if (!financeManagerPresent) missing.push("财务部门负责人");
  if (!hrPresent) missing.push("人力资源角色");

  const levels = LEVEL_ORDER.map((level) => ({
    level,
    label: LEVEL_LABELS[level],
    people: activePeople
      .filter((employee) => employee.level === level)
      .sort((left, right) => left.username.localeCompare(right.username)),
  })).filter((item) => item.people.length > 0);

  return {
    coverage: { filled: 4 - missing.length, total: 4, missing },
    levels,
  };
}
