import {
  answerFromEvent,
  decideChatBusinessEffect,
  formatAssistantResult,
  presentAssistantResult,
  presentFormPreview,
  routeForKey,
} from "./assistantPresentation.ts";

function assertEqual(actual: unknown, expected: unknown): void {
  if (actual !== expected) throw new Error(`Expected ${String(expected)}, got ${String(actual)}`);
}

assertEqual(
  answerFromEvent({ node: "final", status: "completed", answer: "今天共有 4 条考勤记录。" }),
  "今天共有 4 条考勤记录。",
);
assertEqual(
  formatAssistantResult("attendance_summary", {
    date: "2026-08-31",
    active_employees: 12,
    recorded: 4,
    missing: 8,
    status_counts: { present: 2, late: 1, absent: 0, remote: 1 },
  }),
  "2026-08-31 考勤：应出勤 12 人，已登记 4 人，未登记 8 人；正常 2、迟到 1、缺勤 0、远程 1。",
);
assertEqual(answerFromEvent({ node: "answer", status: "streaming", delta: "正在回答" }), "正在回答");

// 历史区间：月度考勤和月度费用要显示自己的区间，不能退回“今日”
assertEqual(
  formatAssistantResult("attendance_summary", {
    month: "2026-08",
    period_start: "2026-08-01",
    period_end: "2026-08-31",
    active_employees: 10,
    records: 23,
    days_recorded: 12,
    employees_recorded: 8,
    status_counts: { present: 20, late: 2, absent: 1, remote: 0 },
  }),
  "2026-08 考勤：在职员工 10 人，共 23 条记录，覆盖 12 天、8 人；正常 20、迟到 2、缺勤 1、远程 0。",
);
assertEqual(
  formatAssistantResult("expense_summary", {
    month: "2026-08",
    count: 3,
    amount: "1286.00",
    status_counts: { paid: 2, draft: 1 },
  }),
  "2026-08 费用：共 3 笔，金额 ¥1286.00；草稿 1、待审批 0、待付款 0、已付款 2。",
);
assertEqual(presentAssistantResult("attendance_summary", { month: "2026-08" }).title, "考勤汇总");

// 周/滚动区间没有月份键，必须显示自己的起止日期
assertEqual(
  formatAssistantResult("attendance_summary", {
    period_start: "2026-08-24",
    period_end: "2026-08-30",
    active_employees: 10,
    records: 6,
    days_recorded: 3,
    employees_recorded: 4,
    status_counts: { present: 5, late: 1, absent: 0, remote: 0 },
  }),
  "2026-08-24 至 2026-08-30 考勤：在职员工 10 人，共 6 条记录，覆盖 3 天、4 人；正常 5、迟到 1、缺勤 0、远程 0。",
);
assertEqual(
  formatAssistantResult("expense_summary", {
    period_start: "2026-08-24",
    period_end: "2026-08-30",
    count: 1,
    amount: "120.00",
    status_counts: { paid: 1 },
  }),
  "2026-08-24 至 2026-08-30 费用：共 1 笔，金额 ¥120.00；草稿 0、待审批 0、待付款 0、已付款 1。",
);assertEqual(routeForKey("admin", "overview"), "/admin/overview");
assertEqual(routeForKey("employee", "tickets"), "/collaboration");
assertEqual(routeForKey("employee", "projects"), null);
assertEqual(routeForKey("admin", "expenses", { month: "2026-09", path: "/evil" }), "/admin/expenses?month=2026-09");
assertEqual(routeForKey("admin", "https://example.com"), null);

const navigation = decideChatBusinessEffect(
  { node: "navigation", status: "ready", route_key: "tickets", display: "正在打开工单中心。" },
  "employee",
);
assertEqual(navigation.kind, "navigation");
assertEqual(navigation.kind === "navigation" ? navigation.href : null, "/collaboration");

const query = decideChatBusinessEffect(
  {
    node: "query_result",
    status: "completed",
    intent: "expense_summary",
    result: { month: "2026-09", count: 2, amount: "188.00", status_counts: { paid: 1, draft: 1 } },
  },
  "employee",
);
assertEqual(query.kind, "result");
assertEqual(
  query.kind === "result" ? query.summary : null,
  "2026-09 费用：共 2 笔，金额 ¥188.00；草稿 1、待审批 0、待付款 0、已付款 1。",
);

const unknown = decideChatBusinessEffect(
  { node: "navigation", status: "ready", route_key: "javascript:alert(1)" },
  "admin",
);
assertEqual(unknown.kind, "none");

// 列表查询要在卡片里给出前几条真实结果，并给出可跳转的封闭路由
const projects = presentAssistantResult("list_projects", {
  count: 2,
  items: [
    { id: "p1", name: "研发项目", code: "A", status: "active" },
    { id: "p2", name: "财务项目" },
    { id: "p3" },
  ],
});
assertEqual(projects.title, "项目列表");
assertEqual(projects.lines.length, 3);
assertEqual(projects.lines[1], "研发项目（A · active）");
assertEqual(projects.lines[2], "财务项目");
assertEqual(projects.routeKey, "projects");
assertEqual(presentAssistantResult("attendance_summary", { date: "2026-09-01" }).routeKey, undefined);

// 没有提交弹窗的界面（管理助手）需要看到抽取出的表单字段
const form = presentFormPreview("leave", {
  is_leave_request: true,
  leave_type: "事假",
  start_date: "2026-09-02",
  end_date: "2026-09-03",
  reason: "家里有事",
});
assertEqual(form.title, "请假表单预览");
assertEqual(form.lines[0], "类型：事假");
assertEqual(form.lines.length, 4);
assertEqual(presentFormPreview("ticket", { is_ticket_request: false }).lines.length, 1);
