import type { EmploymentStatus, OrgMembership } from "./types";

const STATUS_LABELS: Record<EmploymentStatus, string> = {
  probation: "试用期",
  active: "在职",
  suspended: "停职",
  terminated: "已离职",
};

export function formatEmploymentStatus(status: string): string {
  return STATUS_LABELS[status as EmploymentStatus] ?? "未知状态";
}

export function formatOrgMemberships(memberships: OrgMembership[]): string[] {
  return memberships.map((membership) => {
    const position = membership.position ? ` · ${membership.position}` : "";
    const primary = membership.is_primary ? "（主部门）" : "";
    return `${membership.department_name}${position}${primary}`;
  });
}

export function formatEmployeeDisplayName(employee: {
  username: string;
  full_name: string;
  status: string;
}): string {
  const name = employee.full_name.trim() || employee.username;
  return employee.status === "terminated" ? `${name}（已离职）` : name;
}
