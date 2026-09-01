import {
  decideChatPageOutcome,
  fallbackFormForQuestion,
  isActionableFormPreview,
} from "./chatBusinessIntent.ts";

function assertEqual(actual: unknown, expected: unknown): void {
  if (actual !== expected) throw new Error(`Expected ${String(expected)}, got ${String(actual)}`);
}

// 导航：员工看到的是自己的协作页，不是管理端路由
const navigate = decideChatPageOutcome(
  { node: "navigation", status: "ready", route_key: "tickets", display: "正在打开工单中心。" },
  "employee",
);
assertEqual(navigate.kind, "navigate");
assertEqual(navigate.kind === "navigate" ? navigate.href : null, "/collaboration");

// 表单：识别成功才打开既有弹窗
const leave = decideChatPageOutcome(
  {
    node: "form_preview",
    status: "ready",
    form: "leave",
    preview: { is_leave_request: true, leave_type: "事假", start_date: "2026-09-02", end_date: "2026-09-03", reason: "家里有事" },
  },
  "employee",
);
assertEqual(leave.kind, "form");
assertEqual(leave.kind === "form" ? leave.form : null, "leave");

const ticket = decideChatPageOutcome(
  {
    node: "form_preview",
    status: "ready",
    form: "ticket",
    display: "已整理工单表单预览，请确认内容后再提交。",
    preview: { is_ticket_request: false },
  },
  "employee",
);
assertEqual(ticket.kind, "message");
assertEqual(ticket.kind === "message" ? ticket.content : null, "已整理工单表单预览，请确认内容后再提交。");

assertEqual(isActionableFormPreview("expense", { is_expense_request: true }), true);
assertEqual(isActionableFormPreview("expense", { is_expense_request: false }), false);
assertEqual(isActionableFormPreview("expense", null), false);

// 实时查询：正文是可读摘要，卡片带结构化结果
const query = decideChatPageOutcome(
  {
    node: "query_result",
    status: "completed",
    intent: "expense_summary",
    result: { month: "2026-09", count: 2, amount: "188.00", status_counts: { paid: 1, draft: 1 } },
  },
  "employee",
);
assertEqual(query.kind, "message");
assertEqual(
  query.kind === "message" ? query.content : null,
  "2026-09 费用：共 2 笔，金额 ¥188.00；草稿 1、待审批 0、待付款 0、已付款 1。",
);
assertEqual(query.kind === "message" ? query.result?.title : null, "费用汇总");

// 受控动作：预览必须带 action_id 与参数哈希，前端不得自行确认
const action = decideChatPageOutcome(
  {
    node: "action_preview",
    status: "ready",
    action_id: "action-1",
    tool_name: "create_leave_request",
    risk_level: "high",
    summary: "创建请假申请",
    confirmation_step: 0,
    confirmation_steps_required: 1,
    parameter_hash: "hash",
    confirmation_phrase: "确认执行",
  },
  "employee",
);
assertEqual(action.kind, "action");
assertEqual(action.kind === "action" ? action.preview.action_id : null, "action-1");
assertEqual(action.kind === "action" ? action.preview.parameter_hash : null, "hash");

// 澄清与无关事件
assertEqual(
  decideChatPageOutcome({ node: "clarification", status: "ready", display: "请补充具体业务。" }, "employee").kind,
  "message",
);
assertEqual(decideChatPageOutcome({ node: "retrieval", status: "running" }, "employee").kind, "none");
assertEqual(
  decideChatPageOutcome({ node: "navigation", status: "ready", route_key: "javascript:alert(1)" }, "employee").kind,
  "none",
);

// 兜底：只有后端没有给出业务事件时才用本地规则
assertEqual(fallbackFormForQuestion("我要请假两天"), "leave");
assertEqual(fallbackFormForQuestion("报销打车 86 元"), "expense");
assertEqual(fallbackFormForQuestion("帮我处理一下这个工单"), "ticket");
assertEqual(fallbackFormForQuestion("公司的请假制度是什么"), null);
