// 员工聊天页对后端统一业务事件的纯函数解释层。
// 后端已经决定了"这句话属于哪种能力"，这里只负责把事件翻译成页面效果：
// 跳转、打开既有表单弹窗、追加一条可读消息，或渲染受控动作确认卡。
import { decideChatBusinessEffect } from "./assistantPresentation.ts";
import type { AssistantResultPresentation } from "./assistantPresentation.ts";
import { shouldPreviewLeave } from "./scheduleFormat.ts";
import { shouldPreviewExpense, shouldPreviewTicket } from "./chatIntent.ts";
import type {
  AssistantActionPreview,
  ExpensePreview,
  LeavePreview,
  PipelineEvent,
  Role,
  TicketPreview,
} from "./types/index.ts";

export type ChatFormKind = "leave" | "ticket" | "expense";
export type ChatFormPreview = LeavePreview | TicketPreview | ExpensePreview;

export type ChatBusinessOutcome =
  | { kind: "none" }
  | { kind: "navigate"; href: string; notice: string }
  | { kind: "form"; form: ChatFormKind; preview: ChatFormPreview }
  | { kind: "message"; content: string; result?: AssistantResultPresentation }
  | { kind: "action"; preview: AssistantActionPreview; content: string };

const FORM_FLAGS: Record<ChatFormKind, string> = {
  leave: "is_leave_request",
  ticket: "is_ticket_request",
  expense: "is_expense_request",
};

/** A preview whose own recognition flag is false must not open an empty dialog. */
export function isActionableFormPreview(form: ChatFormKind, preview: unknown): boolean {
  if (typeof preview !== "object" || preview === null) return false;
  return (preview as Record<string, unknown>)[FORM_FLAGS[form]] === true;
}

export function decideChatPageOutcome(event: PipelineEvent, role: Role): ChatBusinessOutcome {
  const effect = decideChatBusinessEffect(event, role);
  if (effect.kind === "navigation") {
    return { kind: "navigate", href: effect.href, notice: effect.display };
  }
  if (effect.kind === "form") {
    return isActionableFormPreview(effect.form, effect.preview)
      ? { kind: "form", form: effect.form, preview: effect.preview }
      : { kind: "message", content: effect.display };
  }
  if (effect.kind === "result") {
    return { kind: "message", content: effect.summary, result: effect.presentation };
  }
  if (effect.kind === "action") {
    return { kind: "action", preview: effect.preview, content: effect.display };
  }
  if (effect.kind === "clarification") {
    return { kind: "message", content: effect.display };
  }
  return { kind: "none" };
}

/**
 * Legacy client-side detection, kept only for a backend that emits no business
 * event.  The server rules are authoritative whenever they answer.
 */
export function fallbackFormForQuestion(question: string): ChatFormKind | null {
  if (shouldPreviewLeave(question)) return "leave";
  if (shouldPreviewExpense(question)) return "expense";
  if (shouldPreviewTicket(question)) return "ticket";
  return null;
}
