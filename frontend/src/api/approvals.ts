import { apiClient } from "./client";
import type {
  ApprovalActionType,
  ApprovalHistoryItem,
  ApprovalInstance,
  ApprovalTask,
} from "../types";

export async function listApprovalInbox(): Promise<ApprovalTask[]> {
  const response = await apiClient.get<ApprovalTask[]>("/approvals/inbox");
  return response.data;
}

export async function listSubmittedApprovals(): Promise<ApprovalInstance[]> {
  const response = await apiClient.get<ApprovalInstance[]>("/approvals/submitted");
  return response.data;
}

export async function listApprovalHistory(): Promise<ApprovalHistoryItem[]> {
  const response = await apiClient.get<ApprovalHistoryItem[]>("/approvals/history");
  return response.data;
}

export async function getApproval(id: string): Promise<ApprovalInstance> {
  const response = await apiClient.get<ApprovalInstance>(`/approvals/${id}`);
  return response.data;
}

async function approvalAction(
  id: string,
  action: Exclude<ApprovalActionType, "submit">,
  expectedVersion: number,
  comment: string,
): Promise<ApprovalInstance> {
  const response = await apiClient.post<ApprovalInstance>(`/approvals/${id}/${action}`, {
    expected_version: expectedVersion,
    comment,
  });
  return response.data;
}

export const approveApproval = (id: string, version: number, comment: string) =>
  approvalAction(id, "approve", version, comment);
export const rejectApproval = (id: string, version: number, comment: string) =>
  approvalAction(id, "reject", version, comment);
export const cancelApproval = (id: string, version: number, comment: string) =>
  approvalAction(id, "cancel", version, comment);
