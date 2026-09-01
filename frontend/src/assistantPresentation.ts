import type {
  AssistantActionPreview,
  ExpensePreview,
  LeavePreview,
  PipelineEvent,
  Role,
  TicketPreview,
} from "./types";

export type AssistantRouteKey =
  | "tickets"
  | "expenses"
  | "organization"
  | "projects"
  | "contracts"
  | "knowledge"
  | "schedules"
  | "payroll"
  | "overview"
  | "assistant";

type RouteParams = Record<string, string | number | boolean | null | undefined>;

export interface AssistantResultPresentation {
  title: string;
  summary: string;
  lines: string[];
  routeKey?: AssistantRouteKey;
}

export type ChatBusinessEffect =
  | { kind: "none" }
  | { kind: "navigation"; href: string; display: string }
  | { kind: "form"; form: "leave" | "ticket" | "expense"; preview: LeavePreview | TicketPreview | ExpensePreview; display: string }
  | { kind: "result"; presentation: AssistantResultPresentation; summary: string }
  | { kind: "action"; preview: AssistantActionPreview; display: string }
  | { kind: "clarification"; display: string };

const ADMIN_ROUTES: Record<AssistantRouteKey, string> = {
  tickets: "/admin/tickets",
  expenses: "/admin/expenses",
  organization: "/admin/organization",
  projects: "/admin/projects",
  contracts: "/admin/contracts",
  knowledge: "/admin/knowledge",
  schedules: "/admin/work-schedules",
  payroll: "/admin/payroll",
  overview: "/admin/overview",
  assistant: "/admin/assistant",
};

const EMPLOYEE_ROUTES: Partial<Record<AssistantRouteKey, string>> = {
  tickets: "/collaboration",
  expenses: "/expenses",
  organization: "/organization",
  overview: "/dashboard",
  assistant: "/chat",
};

const QUERY_PARAMS: Partial<Record<AssistantRouteKey, readonly string[]>> = {
  expenses: ["status", "department", "month", "start", "end", "expense"],
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function text(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function routeKey(value: unknown): AssistantRouteKey | null {
  return typeof value === "string" && value in ADMIN_ROUTES ? (value as AssistantRouteKey) : null;
}

function statusCount(result: Record<string, unknown>, status: string): number {
  const counts = result.status_counts;
  return isRecord(counts) && numberValue(counts[status]) !== null ? numberValue(counts[status])! : 0;
}

export function routeForKey(role: Role, key: unknown, params: RouteParams = {}): string | null {
  const validatedKey = routeKey(key);
  if (validatedKey === null) return null;
  const base = role === "admin" ? ADMIN_ROUTES[validatedKey] : EMPLOYEE_ROUTES[validatedKey];
  if (!base) return null;
  const allowed = new Set(QUERY_PARAMS[validatedKey] ?? []);
  const search = new URLSearchParams();
  for (const [name, value] of Object.entries(params)) {
    if (!allowed.has(name) || value === null || value === undefined) continue;
    search.set(name, String(value));
  }
  const encoded = search.toString();
  return encoded ? `${base}?${encoded}` : base;
}

export function answerFromEvent(event: PipelineEvent): string | null {
  if (event.node === "answer" && event.status === "streaming") return text(event.delta);
  if (event.node === "final") return text(event.answer);
  return text(event.display);
}

function periodLabel(result: Record<string, unknown>, fallback: string): string {
  const month = text(result.month);
  if (month !== null) return month;
  const start = text(result.period_start);
  const end = text(result.period_end);
  if (start !== null && end !== null) return `${start} 至 ${end}`;
  return fallback;
}

export function formatAssistantResult(intent: unknown, value: unknown): string {
  const result = isRecord(value) ? value : {};
  const statuses = `正常 ${statusCount(result, "present")}、迟到 ${statusCount(result, "late")}、缺勤 ${statusCount(result, "absent")}、远程 ${statusCount(result, "remote")}。`;
  if (intent === "attendance_summary") {
    const date = text(result.date);
    if (date !== null) {
      return `${date} 考勤：应出勤 ${numberValue(result.active_employees) ?? 0} 人，已登记 ${numberValue(result.recorded) ?? 0} 人，未登记 ${numberValue(result.missing) ?? 0} 人；${statuses}`;
    }
    return `${periodLabel(result, "本期")} 考勤：在职员工 ${numberValue(result.active_employees) ?? 0} 人，共 ${numberValue(result.records) ?? 0} 条记录，覆盖 ${numberValue(result.days_recorded) ?? 0} 天、${numberValue(result.employees_recorded) ?? 0} 人；${statuses}`;
  }
  if (intent === "expense_summary") {
    return `${periodLabel(result, "本月")} 费用：共 ${numberValue(result.count) ?? 0} 笔，金额 ¥${text(result.amount) ?? "0.00"}；草稿 ${statusCount(result, "draft")}、待审批 ${statusCount(result, "pending_approval")}、待付款 ${statusCount(result, "payment_pending")}、已付款 ${statusCount(result, "paid")}。`;
  }
  if (typeof result.count === "number") return `查询完成，共找到 ${result.count} 条结果。`;
  return "查询完成，结果已返回。";
}

const INTENT_TITLES: Record<string, string> = {
  attendance_summary: "考勤汇总",
  expense_summary: "费用汇总",
  list_projects: "项目列表",
  list_contracts: "合同列表",
  list_departments: "部门列表",
  list_tickets: "工单列表",
  list_expenses: "费用列表",
  list_approvals: "审批列表",
};

// 列表意图对应的可跳转页面：只用这张封闭表，绝不接受服务端或模型给出的 URL。
const INTENT_ROUTES: Record<string, AssistantRouteKey> = {
  expense_summary: "expenses",
  list_projects: "projects",
  list_contracts: "contracts",
  list_departments: "organization",
  list_tickets: "tickets",
  list_expenses: "expenses",
  list_approvals: "expenses",
};

function itemLabel(item: Record<string, unknown>): string | null {
  const name =
    text(item.name) ?? text(item.title) ?? text(item.subject) ?? text(item.full_name) ?? text(item.username);
  if (name === null) return null;
  const details = [text(item.code), text(item.status), text(item.amount) && `¥${text(item.amount)}`]
    .filter((value): value is string => Boolean(value))
    .join(" · ");
  return details ? `${name}（${details}）` : name;
}

export function presentAssistantResult(intent: unknown, value: unknown): AssistantResultPresentation {
  const summary = formatAssistantResult(intent, value);
  const result = isRecord(value) ? value : {};
  const intentName = typeof intent === "string" ? intent : "";
  const rows = (Array.isArray(result.items) ? result.items.filter(isRecord) : [])
    .map(itemLabel)
    .filter((line): line is string => line !== null)
    .slice(0, 5);
  return {
    title: INTENT_TITLES[intentName] ?? "查询结果",
    summary,
    lines: [summary, ...rows],
    routeKey: routeKey(result.route_key) ?? INTENT_ROUTES[intentName],
  };
}

const FORM_TITLES: Record<"leave" | "ticket" | "expense", string> = {
  leave: "请假表单预览",
  ticket: "工单表单预览",
  expense: "报销表单预览",
};

const FORM_FIELDS: Record<"leave" | "ticket" | "expense", readonly [string, string][]> = {
  leave: [
    ["leave_type", "类型"],
    ["start_date", "开始日期"],
    ["end_date", "结束日期"],
    ["reason", "事由"],
  ],
  ticket: [
    ["ticket_type", "工单类型"],
    ["subject", "主题"],
    ["target_username", "处理人"],
    ["department_name", "部门"],
  ],
  expense: [
    ["title", "标题"],
    ["total_amount", "金额"],
    ["category", "类别"],
    ["purpose", "用途"],
  ],
};

/** Render extracted form fields for surfaces that have no submission dialog. */
export function presentFormPreview(
  form: "leave" | "ticket" | "expense",
  preview: unknown,
): AssistantResultPresentation {
  const record = isRecord(preview) ? preview : {};
  const lines = FORM_FIELDS[form]
    .map(([field, label]) => {
      const value = record[field];
      const rendered = typeof value === "number" ? String(value) : text(value);
      return rendered === null ? null : `${label}：${rendered}`;
    })
    .filter((line): line is string => line !== null);
  return {
    title: FORM_TITLES[form],
    summary: lines.length > 0 ? lines.join("；") : "未能从这句话中提取到足够的字段。",
    lines: lines.length > 0 ? lines : ["未能从这句话中提取到足够的字段，请补充具体信息。"],
  };
}

function formEffect(event: PipelineEvent): ChatBusinessEffect | null {
  if (event.node !== "form_preview") return null;
  const form = text(event.form);
  const preview = event.preview;
  if ((form !== "leave" && form !== "ticket" && form !== "expense") || !isRecord(preview)) return { kind: "none" };
  return {
    kind: "form",
    form,
    preview: preview as unknown as LeavePreview | TicketPreview | ExpensePreview,
    display: text(event.display) ?? "已生成表单预览，请确认内容后再提交。",
  };
}

function actionPreview(event: PipelineEvent): AssistantActionPreview | null {
  if (event.node !== "action_preview") return null;
  const actionId = text(event.action_id);
  const toolName = text(event.tool_name);
  const riskLevel = text(event.risk_level);
  const summary = text(event.summary);
  if (!actionId || !toolName || !riskLevel || !summary) return null;
  return {
    action_id: actionId,
    tool_name: toolName,
    risk_level: riskLevel,
    summary,
    confirmation_phrase: text(event.confirmation_phrase),
    confirmation_step: numberValue(event.confirmation_step) ?? 0,
    confirmation_steps_required: numberValue(event.confirmation_steps_required) ?? 1,
    expires_at: text(event.expires_at),
    parameter_hash: text(event.parameter_hash),
    changes: Array.isArray(event.changes) ? event.changes.filter(isRecord).map((change) => ({
      field: text(change.field) ?? "变更",
      before: change.before,
      after: change.after,
    })) : [],
  };
}

export function decideChatBusinessEffect(event: PipelineEvent, role: Role): ChatBusinessEffect {
  if (event.node === "navigation") {
    const href = routeForKey(role, event.route_key);
    return href ? { kind: "navigation", href, display: text(event.display) ?? "正在打开页面。" } : { kind: "none" };
  }
  const form = formEffect(event);
  if (form !== null) return form;
  if (event.node === "query_result") {
    const intent = text(event.intent) ?? "query";
    const result = isRecord(event.result) ? event.result : event.payload;
    const presentation = presentAssistantResult(intent, result);
    return { kind: "result", presentation, summary: presentation.summary };
  }
  const preview = actionPreview(event);
  if (preview !== null) return { kind: "action", preview, display: text(event.display) ?? "操作预览已生成，请确认后执行。" };
  if (event.node === "clarification") return { kind: "clarification", display: text(event.display) ?? "请补充要办理的具体业务和必要信息。" };
  return { kind: "none" };
}
