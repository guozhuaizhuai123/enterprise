import type { DepartmentMembership } from "./types";

export interface AdminNavItem {
  to: string;
  label: string;
}

/**
 * 管理端一级导航。收敛为"管理助手"和"企业全景"两个入口：其余管理页面继续
 * 存在，但只通过助手导航、全景下钻或直接链接进入。
 */
export function primaryAdminRoutes(): AdminNavItem[] {
  return [
    { to: "/admin/assistant", label: "管理助手" },
    { to: "/admin/overview", label: "企业全景" },
  ];
}

/** 企业全景上的"向管理助手提问"链接；参数一律用 URLSearchParams 编码。 */
export function overviewAssistantHref(prompt: string, departmentId?: string | null): string {
  const params = new URLSearchParams({ prompt });
  if (departmentId) params.set("department", departmentId);
  return `/admin/assistant?${params.toString()}`;
}

export function getDepartmentHref(departmentId: string): string {
  return `/admin/departments/${encodeURIComponent(departmentId)}`;
}

export function getEmployeeMembershipLabels(employee: {
  departments?: DepartmentMembership[];
}): string[] {
  return (employee.departments ?? []).map((membership) =>
    membership.position ? `${membership.name} · ${membership.position}` : membership.name,
  );
}

export function formatOwnerLabel(ownerName: string, ownerActive: boolean): string {
  return ownerActive ? ownerName : `${ownerName}（已离职）`;
}

export function canEditOwnedDocument(ownerId: string | null | undefined, userId: string | null): boolean {
  return Boolean(ownerId && userId && ownerId === userId);
}
