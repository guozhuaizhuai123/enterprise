import type { DepartmentMembership } from "./types";

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
