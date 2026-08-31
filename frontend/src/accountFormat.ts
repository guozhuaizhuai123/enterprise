const ROLE_LABELS: Record<string, string> = {
  finance: "财务复核",
  hr: "人力资源",
  manager: "部门负责人",
};

export function formatAccountRoleLabel(baseRole: string, roles: string[]): string {
  if (baseRole === "admin") return "管理员";
  const labels = roles
    .filter((role) => role !== "employee" && role !== "admin")
    .map((role) => ROLE_LABELS[role] ?? role);
  return labels.length > 0 ? labels.join(" / ") : "员工";
}
