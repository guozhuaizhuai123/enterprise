import { initialAdminAssistantState, reduceAdminAssistantEvent, startAdminAssistantAsk } from "./adminAssistantState.ts";

function assertEqual(actual: unknown, expected: unknown): void {
  if (actual !== expected) throw new Error(`Expected ${String(expected)}, got ${String(actual)}`);
}

let state = startAdminAssistantAsk(initialAdminAssistantState, "查看本月费用", "user-1", "assistant-1");
state = reduceAdminAssistantEvent(state, { node: "thread", status: "ready", thread_id: "thread-1" }, "admin").state;
state = reduceAdminAssistantEvent(state, { node: "retrieval", status: "running" }, "admin").state;
assertEqual(state.threadId, "thread-1");
assertEqual(state.messages.length, 2);
assertEqual(state.messages[1]?.content, "");

state = reduceAdminAssistantEvent(state, { node: "answer", status: "streaming", delta: "正在汇总" }, "admin").state;
state = reduceAdminAssistantEvent(state, { node: "final", status: "completed", answer: "知识答案" }, "admin").state;
assertEqual(state.messages[1]?.content, "知识答案");
assertEqual(state.messages[1]?.streaming, false);

const query = reduceAdminAssistantEvent(
  state,
  { node: "query_result", status: "completed", intent: "expense_summary", result: { month: "2026-09", count: 1, amount: "86.00", status_counts: {} } },
  "admin",
);
assertEqual(query.state.messages[1]?.result?.title, "费用汇总");
assertEqual(query.state.messages[1]?.content, "2026-09 费用：共 1 笔，金额 ¥86.00；草稿 0、待审批 0、待付款 0、已付款 0。");

const action = reduceAdminAssistantEvent(
  query.state,
  { node: "action_preview", status: "ready", action_id: "action-1", tool_name: "create_project", risk_level: "high", summary: "创建项目", confirmation_step: 0, confirmation_steps_required: 1, parameter_hash: "hash", confirmation_phrase: "确认执行" },
  "admin",
);
assertEqual(action.state.action?.action_id, "action-1");
assertEqual(action.state.messages[1]?.content, "操作预览已生成，请确认后执行。");
