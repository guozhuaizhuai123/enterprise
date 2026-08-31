import { API_BASE, apiClient } from "./client";
import { splitSSEBlocks } from "./sse";
import { useAuthStore } from "../store/auth";
import type { PipelineEvent, ThreadContextSettings, AssistantActionResult } from "../types";

export async function confirmAssistantAction(actionId:string, confirmationPhrase:string, parameterHash:string):Promise<AssistantActionResult>{ const r=await apiClient.post(`/chat/actions/${actionId}/confirm`,{action_id:actionId,confirmation_phrase:confirmationPhrase,parameter_hash:parameterHash}); return r.data; }
export async function cancelAssistantAction(actionId:string):Promise<AssistantActionResult>{ const r=await apiClient.post(`/chat/actions/${actionId}/cancel`); return r.data; }

export async function getThreadContextSettings(threadId: string): Promise<ThreadContextSettings> {
  const res = await apiClient.get<ThreadContextSettings>(`/chat/threads/${threadId}/context-settings`);
  return res.data;
}

export async function updateThreadContextSettings(
  threadId: string,
  settings: Partial<ThreadContextSettings>,
): Promise<ThreadContextSettings> {
  const res = await apiClient.patch<ThreadContextSettings>(
    `/chat/threads/${threadId}/context-settings`,
    settings,
  );
  return res.data;
}

export const getThreadContext = getThreadContextSettings;
export const updateThreadContext = updateThreadContextSettings;

export async function askQuestion(
  question: string,
  threadId: string | null,
  onEvent: (evt: PipelineEvent) => void,
  options: {
    initialContext?: ThreadContextSettings;
    signal?: AbortSignal;
  } = {},
): Promise<void> {
  const token = useAuthStore.getState().token;
  const body: Record<string, unknown> = { question, thread_id: threadId };
  if (threadId === null && options.initialContext) {
    body.memory_level = options.initialContext.memory_level;
    body.document_scope_mode = options.initialContext.document_scope_mode;
    body.document_ids = [...options.initialContext.document_ids];
  }
  const res = await fetch(`${API_BASE}/chat/ask`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: token ? `Bearer ${token}` : "",
    },
    body: JSON.stringify(body),
    signal: options.signal,
  });

  if (!res.ok || !res.body) {
    throw new Error(`ask failed: ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  function processBlock(block: string) {
    const dataLines = block
      .split("\n")
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trim());
    if (dataLines.length === 0) return;
    const data = dataLines.join("\n");
    if (data === "[DONE]") return;
    try {
      const evt = JSON.parse(data) as PipelineEvent;
      onEvent(evt);
    } catch {
      // ignore malformed chunk
    }
  }

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      buffer += decoder.decode();
      break;
    }
    buffer += decoder.decode(value, { stream: true });

    const parsed = splitSSEBlocks(buffer);
    buffer = parsed.remainder;
    parsed.blocks.forEach(processBlock);
  }

  splitSSEBlocks(buffer, true).blocks.forEach(processBlock);
}
