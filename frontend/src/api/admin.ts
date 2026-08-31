import { apiClient } from "./client";
import type {
  Department,
  DepartmentMemoryItem,
  DocumentDetail,
  DocumentItem,
  Employee,
  SensitiveEvent,
  SensitiveKeyword,
  UserOption,
} from "../types";

export async function listDepartmentMemories(departmentId: string): Promise<DepartmentMemoryItem[]> {
  const res = await apiClient.get<DepartmentMemoryItem[]>(`/admin/departments/${departmentId}/memories`);
  return res.data;
}

export async function createDepartmentMemory(
  departmentId: string,
  data: { title: string; content: string; enabled?: boolean },
): Promise<DepartmentMemoryItem> {
  const res = await apiClient.post<DepartmentMemoryItem>(`/admin/departments/${departmentId}/memories`, data);
  return res.data;
}

export async function updateDepartmentMemory(
  memoryId: string,
  data: Partial<{ title: string; content: string; enabled: boolean }>,
): Promise<DepartmentMemoryItem> {
  const res = await apiClient.put<DepartmentMemoryItem>(`/admin/department-memories/${memoryId}`, data);
  return res.data;
}

export async function deleteDepartmentMemory(memoryId: string): Promise<void> {
  await apiClient.delete(`/admin/department-memories/${memoryId}`);
}

export async function listDepartments(): Promise<Department[]> {
  const res = await apiClient.get<Department[]>("/admin/departments");
  return res.data;
}

export async function createDepartment(name: string): Promise<Department> {
  const res = await apiClient.post<Department>("/admin/departments", { name });
  return res.data;
}

export async function deleteDepartment(id: string): Promise<void> {
  await apiClient.delete(`/admin/departments/${id}`);
}

export async function listEmployees(departmentId: string): Promise<Employee[]> {
  const res = await apiClient.get<Employee[]>(`/admin/departments/${departmentId}/employees`);
  return res.data;
}

export async function listOwnerOptions(): Promise<UserOption[]> {
  const res = await apiClient.get<UserOption[]>("/admin/users");
  return res.data;
}

export async function listSensitiveEvents(): Promise<SensitiveEvent[]> {
  const res = await apiClient.get<SensitiveEvent[]>("/admin/sensitive-events");
  return res.data;
}

export async function deleteSensitiveEvent(eventId: string): Promise<void> {
  await apiClient.delete(`/admin/sensitive-events/${eventId}`);
}

export async function listSensitiveKeywords(): Promise<SensitiveKeyword[]> {
  const res = await apiClient.get<SensitiveKeyword[]>("/admin/sensitive-keywords");
  return res.data;
}

export async function createSensitiveKeyword(keyword: string): Promise<SensitiveKeyword> {
  const res = await apiClient.post<SensitiveKeyword>("/admin/sensitive-keywords", { keyword });
  return res.data;
}

export async function updateSensitiveKeyword(
  keywordId: string,
  data: { keyword?: string; enabled?: boolean },
): Promise<SensitiveKeyword> {
  const res = await apiClient.put<SensitiveKeyword>(`/admin/sensitive-keywords/${keywordId}`, data);
  return res.data;
}

export async function deleteSensitiveKeyword(keywordId: string): Promise<void> {
  await apiClient.delete(`/admin/sensitive-keywords/${keywordId}`);
}

export async function createEmployee(
  departmentId: string,
  username: string,
  password: string,
  departmentIds: string[],
  positions: Record<string, string>,
): Promise<Employee> {
  const res = await apiClient.post<Employee>(`/admin/departments/${departmentId}/employees`, {
    username,
    password,
    department_ids: departmentIds,
    positions,
  });
  return res.data;
}

export async function updateEmployeePassword(employeeId: string, password: string): Promise<Employee> {
  const res = await apiClient.put<Employee>(`/admin/employees/${employeeId}`, { password });
  return res.data;
}

export async function deleteEmployee(employeeId: string): Promise<void> {
  await apiClient.delete(`/admin/employees/${employeeId}`);
}

export async function listDepartmentDocuments(departmentId: string): Promise<DocumentItem[]> {
  const res = await apiClient.get<DocumentItem[]>(`/admin/departments/${departmentId}/documents`);
  return res.data;
}

export async function listAdminDocuments(params: Record<string, string> = {}): Promise<DocumentItem[]> {
  const res = await apiClient.get<DocumentItem[]>("/admin/documents", { params });
  return res.data;
}

export async function createDocument(
  departmentId: string,
  data: {
    title: string;
    category: string;
    sensitive: boolean;
    content: string;
    owner_id?: string;
    project_id?: string | null;
    contract_id?: string | null;
  },
): Promise<DocumentDetail> {
  const res = await apiClient.post<DocumentDetail>(`/admin/departments/${departmentId}/documents`, data);
  return res.data;
}

export async function getDocument(documentId: string): Promise<DocumentDetail> {
  const res = await apiClient.get<DocumentDetail>(`/admin/documents/${documentId}`);
  return res.data;
}

export async function updateDocument(
  documentId: string,
  data: Partial<{
    title: string;
    category: string;
    sensitive: boolean;
    content: string;
    owner_id: string | null;
    project_id: string | null;
    contract_id: string | null;
  }>,
): Promise<DocumentDetail> {
  const res = await apiClient.put<DocumentDetail>(`/admin/documents/${documentId}`, data);
  return res.data;
}

export async function deleteDocument(documentId: string): Promise<void> {
  await apiClient.delete(`/admin/documents/${documentId}`);
}
