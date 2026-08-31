import { apiClient } from "./client";
import type { Contract, ContractInput, Project, ProjectInput, ProjectWorkspace } from "../types";

export async function listProjects(params: Record<string, string> = {}): Promise<Project[]> {
  const response = await apiClient.get<Project[]>("/projects", { params });
  return response.data;
}

export async function createProject(payload: ProjectInput): Promise<Project> {
  const response = await apiClient.post<Project>("/projects", payload);
  return response.data;
}

export async function updateProject(id: string, payload: Partial<ProjectInput>): Promise<Project> {
  const response = await apiClient.put<Project>(`/projects/${id}`, payload);
  return response.data;
}

export async function deleteProject(id: string): Promise<void> {
  await apiClient.delete(`/projects/${id}`);
}

export async function getProjectWorkspace(id: string): Promise<ProjectWorkspace> {
  const response = await apiClient.get<ProjectWorkspace>(`/projects/${id}/workspace`);
  return response.data;
}

export async function listContracts(params: Record<string, string> = {}): Promise<Contract[]> {
  const response = await apiClient.get<Contract[]>("/contracts", { params });
  return response.data;
}

export async function createContract(payload: ContractInput): Promise<Contract> {
  const response = await apiClient.post<Contract>("/contracts", payload);
  return response.data;
}

export async function updateContract(id: string, payload: Partial<ContractInput>): Promise<Contract> {
  const response = await apiClient.put<Contract>(`/contracts/${id}`, payload);
  return response.data;
}

export async function deleteContract(id: string): Promise<void> {
  await apiClient.delete(`/contracts/${id}`);
}
