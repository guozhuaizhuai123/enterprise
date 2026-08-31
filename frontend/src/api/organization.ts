import { apiClient } from "./client";
import type {
  EmploymentStatus,
  OrgEmployee,
  OrgEmployeeInput,
  OrgEmployeeUpdate,
  OrgUnit,
} from "../types";

export async function listOrgUnits(): Promise<OrgUnit[]> {
  const response = await apiClient.get<OrgUnit[]>("/admin/org-units");
  return response.data;
}

export async function createOrgUnit(data: {
  name: string;
  code: string;
  parent_id?: string | null;
  manager_id?: string | null;
}): Promise<OrgUnit> {
  const response = await apiClient.post<OrgUnit>("/admin/org-units", data);
  return response.data;
}

export async function updateOrgUnit(
  id: string,
  data: Partial<Pick<OrgUnit, "name" | "code" | "parent_id" | "manager_id" | "active">>,
): Promise<OrgUnit> {
  const response = await apiClient.patch<OrgUnit>(`/admin/org-units/${id}`, data);
  return response.data;
}

export async function listOrgEmployees(filters?: {
  departmentId?: string;
  status?: EmploymentStatus | "";
}): Promise<OrgEmployee[]> {
  const response = await apiClient.get<OrgEmployee[]>("/admin/employees", {
    params: {
      department_id: filters?.departmentId || undefined,
      status: filters?.status || undefined,
    },
  });
  return response.data;
}

export async function getOrgEmployee(id: string): Promise<OrgEmployee> {
  const response = await apiClient.get<OrgEmployee>(`/admin/employees/${id}`);
  return response.data;
}

export async function createOrgEmployee(data: OrgEmployeeInput): Promise<OrgEmployee> {
  const response = await apiClient.post<OrgEmployee>("/admin/employees", data);
  return response.data;
}

export async function updateOrgEmployee(
  id: string,
  data: OrgEmployeeUpdate,
): Promise<OrgEmployee> {
  const response = await apiClient.patch<OrgEmployee>(`/admin/employees/${id}`, data);
  return response.data;
}

export async function resetEmployeePassword(id: string, password: string): Promise<void> {
  await apiClient.post(`/admin/employees/${id}/reset-password`, { password });
}

export async function offboardEmployee(
  id: string,
  data: { effective_date: string; note: string },
): Promise<void> {
  await apiClient.post(`/admin/employees/${id}/events`, {
    event_type: "offboard",
    status: "terminated",
    ...data,
  });
}
