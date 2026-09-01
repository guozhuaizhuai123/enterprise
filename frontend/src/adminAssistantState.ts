import {
  answerFromEvent,
  decideChatBusinessEffect,
  presentFormPreview,
  type AssistantResultPresentation,
  type ChatBusinessEffect,
} from "./assistantPresentation.ts";
import type { AssistantActionPreview, Citation, PipelineEvent, Role } from "./types/index.ts";

export interface AssistantChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  streaming?: boolean;
  result?: AssistantResultPresentation;
}

export interface AdminAssistantState {
  threadId: string | null;
  activeAssistantId: string | null;
  messages: AssistantChatMessage[];
  action: AssistantActionPreview | null;
}

export const initialAdminAssistantState: AdminAssistantState = {
  threadId: null,
  activeAssistantId: null,
  messages: [],
  action: null,
};

export function startAdminAssistantAsk(
  state: AdminAssistantState,
  question: string,
  userMessageId: string,
  assistantMessageId: string,
): AdminAssistantState {
  return {
    ...state,
    activeAssistantId: assistantMessageId,
    action: null,
    messages: [
      ...state.messages,
      { id: userMessageId, role: "user", content: question },
      { id: assistantMessageId, role: "assistant", content: "", streaming: true },
    ],
  };
}

function updateActiveMessage(
  state: AdminAssistantState,
  update: (message: AssistantChatMessage) => AssistantChatMessage,
): AdminAssistantState {
  if (state.activeAssistantId === null) return state;
  return {
    ...state,
    messages: state.messages.map((message) =>
      message.id === state.activeAssistantId ? update(message) : message,
    ),
  };
}

export function reduceAdminAssistantEvent(
  state: AdminAssistantState,
  event: PipelineEvent,
  role: Role,
): { state: AdminAssistantState; effect: ChatBusinessEffect } {
  if (event.node === "thread" && event.status === "ready" && typeof event.thread_id === "string") {
    return { state: { ...state, threadId: event.thread_id }, effect: { kind: "none" } };
  }
  if (event.node === "answer") {
    const answer = answerFromEvent(event);
    if (answer === null) return { state, effect: { kind: "none" } };
    const next = updateActiveMessage(state, (message) => ({
      ...message,
      content: event.status === "streaming" ? message.content + answer : answer,
      citations: Array.isArray(event.citations_meta) ? event.citations_meta as Citation[] : message.citations,
      streaming: event.status === "streaming",
    }));
    return { state: next, effect: { kind: "none" } };
  }
  if (event.node === "final") {
    const answer = answerFromEvent(event);
    return {
      state: answer === null ? updateActiveMessage(state, (message) => ({ ...message, streaming: false })) : updateActiveMessage(
        state,
        (message) => ({
          ...message,
          content: answer,
          citations: Array.isArray(event.citations) ? event.citations as Citation[] : message.citations,
          streaming: false,
        }),
      ),
      effect: { kind: "none" },
    };
  }

  const effect = decideChatBusinessEffect(event, role);
  if (effect.kind === "none") return { state, effect };
  if (effect.kind === "action") {
    return {
      state: updateActiveMessage({ ...state, action: effect.preview }, (message) => ({
        ...message,
        content: effect.display,
        streaming: false,
      })),
      effect,
    };
  }
  if (effect.kind === "result") {
    return {
      state: updateActiveMessage(state, (message) => ({
        ...message,
        content: effect.summary,
        result: effect.presentation,
        streaming: false,
      })),
      effect,
    };
  }
  if (effect.kind === "form") {
    // 管理助手没有员工端的提交弹窗，所以把提取到的字段直接列出来
    return {
      state: updateActiveMessage(state, (message) => ({
        ...message,
        content: effect.display,
        result: presentFormPreview(effect.form, effect.preview),
        streaming: false,
      })),
      effect,
    };
  }
  return {
    state: updateActiveMessage(state, (message) => ({ ...message, content: effect.display, streaming: false })),
    effect,
  };
}
