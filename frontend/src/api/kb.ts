import { apiClient } from "./client";
import type { DocumentDetail, DocumentItem, MessageItem, ThreadItem } from "../types";

export async function listMyDocuments(): Promise<DocumentItem[]> {
  const res = await apiClient.get<DocumentItem[]>("/kb/documents");
  return res.data;
}

export async function getMyDocument(documentId: string): Promise<DocumentDetail> {
  const res = await apiClient.get<DocumentDetail>(`/kb/documents/${documentId}`);
  return res.data;
}

export async function createMyDocument(data: {
  department_id: string;
  title: string;
  category: string;
  sensitive: boolean;
  content: string;
  project_id?: string | null;
  contract_id?: string | null;
}): Promise<DocumentDetail> {
  const res = await apiClient.post<DocumentDetail>("/kb/documents", data);
  return res.data;
}

export async function updateMyDocument(
  documentId: string,
  data: Partial<{
    title: string;
    category: string;
    sensitive: boolean;
    content: string;
    project_id: string | null;
    contract_id: string | null;
  }>,
): Promise<DocumentDetail> {
  const res = await apiClient.put<DocumentDetail>(`/kb/documents/${documentId}`, data);
  return res.data;
}

export async function deleteMyDocument(documentId: string): Promise<void> {
  await apiClient.delete(`/kb/documents/${documentId}`);
}

export async function listThreads(): Promise<ThreadItem[]> {
  const res = await apiClient.get<ThreadItem[]>("/chat/threads");
  return res.data;
}

export async function deleteThread(threadId: string): Promise<void> {
  await apiClient.delete(`/chat/threads/${threadId}`);
}

export async function listMessages(threadId: string): Promise<MessageItem[]> {
  const res = await apiClient.get<MessageItem[]>(`/chat/threads/${threadId}/messages`);
  return res.data;
}
