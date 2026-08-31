import { apiClient } from "./client";
import type { MemoryItem, UserChatSettings } from "../types";

export async function listUserMemories(): Promise<MemoryItem[]> {
  const res = await apiClient.get<MemoryItem[]>("/me/memories");
  return res.data;
}

export async function createUserMemory(data: {
  title: string;
  content: string;
  enabled?: boolean;
}): Promise<MemoryItem> {
  const res = await apiClient.post<MemoryItem>("/me/memories", data);
  return res.data;
}

export async function updateUserMemory(
  memoryId: string,
  data: Partial<{ title: string; content: string; enabled: boolean }>,
): Promise<MemoryItem> {
  const res = await apiClient.put<MemoryItem>(`/me/memories/${memoryId}`, data);
  return res.data;
}

export async function deleteUserMemory(memoryId: string): Promise<void> {
  await apiClient.delete(`/me/memories/${memoryId}`);
}

export async function getChatSettings(): Promise<UserChatSettings> {
  const res = await apiClient.get<UserChatSettings>("/me/chat-settings");
  return res.data;
}

export async function updateChatSettings(data: Partial<UserChatSettings>): Promise<UserChatSettings> {
  const res = await apiClient.patch<UserChatSettings>("/me/chat-settings", data);
  return res.data;
}

// Short aliases keep the client convenient for screens that already establish the user scope.
export const listMemories = listUserMemories;
export const createMemory = createUserMemory;
export const updateMemory = updateUserMemory;
export const deleteMemory = deleteUserMemory;
