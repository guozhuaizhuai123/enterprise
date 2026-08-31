const STATUS_LABELS: Record<string, string> = {
  pending_approval: "审批中",
  approved: "已通过",
  rejected: "已驳回",
  cancelled: "已撤回",
  pending: "待处理",
};

const ACTION_LABELS: Record<string, string> = {
  submit: "提交申请",
  approve: "审批通过",
  reject: "驳回申请",
  cancel: "撤回申请",
};

export type ApprovalDecisionAction = "approve" | "reject" | "cancel";

export interface ApprovalConfirmation {
  action: ApprovalDecisionAction;
  comment: string;
  title: string;
  confirmLabel: string;
}

export function approvalConfirmation(
  action: ApprovalDecisionAction,
  comment: string,
): ApprovalConfirmation {
  const copy = action === "approve"
    ? { title: "确认通过这项申请？", confirmLabel: "确认通过" }
    : action === "reject"
      ? { title: "确认驳回这项申请？", confirmLabel: "确认驳回" }
      : { title: "确认撤回这项申请？", confirmLabel: "确认撤回" };
  return { action, comment, ...copy };
}

export function formatApprovalStatus(status: string): string {
  return STATUS_LABELS[status] ?? status;
}

export function formatApprovalAction(action: string): string {
  return ACTION_LABELS[action] ?? action;
}

export function formatApprovalCounts(inboxCount: number, submittedCount: number): string {
  return `待我审批 ${inboxCount} · 我发起 ${submittedCount}`;
}

export function defaultApprovalSelection(
  selectedId: string | null,
  tab: "inbox" | "submitted" | "history",
  inboxIds: string[],
  submittedIds: string[],
): string | null {
  if (selectedId) return null;
  // 审批历史只做查看，不自动选中任何一条，避免一进页就多发一次详情请求。
  if (tab === "history") return null;
  return tab === "inbox" ? (inboxIds[0] ?? null) : (submittedIds[0] ?? null);
}

function handlerLabel(step: import("./types").ApprovalRouteStep | undefined): string {
  if (!step || step.handlers.length === 0) return "暂未配置处理人";
  return step.handlers
    .map((handler) => `${handler.display_name}（${handler.username}）`)
    .join("、");
}

export function approvalRouteSummary(route: import("./types").ApprovalRouteStep[] | undefined): {
  current: string;
  next: string;
  final: string;
} {
  const steps = route ?? [];
  const currentIndex = steps.findIndex((step) => step.status === "pending");
  const current = currentIndex >= 0 ? steps[currentIndex] : steps.find((step) => step.status === "upcoming");
  const next = currentIndex >= 0
    ? steps.slice(currentIndex + 1).find((step) => step.status === "upcoming" || step.status === "pending")
    : undefined;
  return {
    current: handlerLabel(current),
    // 没有下一节点是正常的终点，不应被误报为缺少处理人。
    next: next ? handlerLabel(next) : "",
    final: handlerLabel(steps.at(-1)),
  };
}

export interface ApprovalProgressModel {
  current: import("./types").ApprovalRouteStep | undefined;
  upcoming: import("./types").ApprovalRouteStep[];
  completed: import("./types").ApprovalRouteStep[];
  outcome: string;
}

/** Derive the user-facing state from both workflow status and the route steps. */
export function approvalProgressModel(
  instanceStatus: string,
  route: import("./types").ApprovalRouteStep[] | undefined,
  expenseStatus?: string,
): ApprovalProgressModel {
  const steps = route ?? [];
  const current = steps.find((step) => step.status === "pending");
  const upcoming = steps.filter((step) => step.status === "upcoming");
  const completed = steps.filter((step) => step.status === "approved");
  let outcome = "待审批";

  if (expenseStatus === "paid") outcome = "已付款";
  else if (expenseStatus === "payment_pending") outcome = "审批已通过，待付款";
  else if (instanceStatus === "rejected" || steps.some((step) => step.status === "rejected")) outcome = "已驳回";
  else if (instanceStatus === "cancelled" || steps.some((step) => step.status === "cancelled")) outcome = "已撤回";
  else if (current) outcome = current.name === "财务付款" ? "审批已通过，待付款" : `等待${current.name}处理`;
  else if (instanceStatus === "approved") outcome = "审批已通过";

  return { current, upcoming, completed, outcome };
}
