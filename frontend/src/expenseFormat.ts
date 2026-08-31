const STATUS_LABELS: Record<string, string> = {
  draft: "草稿",
  pending_approval: "审批中",
  rejected: "已驳回",
  payment_pending: "待付款",
  paid: "已付款",
  cancelled: "已撤回",
};

function decimalToCents(value: string): number | null {
  const normalized = value.trim();
  if (!/^\d+(?:\.\d+)?$/.test(normalized)) return null;
  const [whole, fraction = ""] = normalized.split(".");
  const thousandths = Number(`${(fraction + "000").slice(0, 3)}`);
  const roundedFraction = Math.floor((thousandths + 5) / 10);
  return Number(whole) * 100 + roundedFraction;
}

export function sumExpenseAmounts(values: string[]): string | null {
  if (values.length === 0) return null;
  let total = 0;
  for (const value of values) {
    const cents = decimalToCents(value);
    if (cents === null || cents <= 0) return null;
    total += cents;
  }
  return (total / 100).toFixed(2);
}

export function formatExpenseStatus(status: string): string {
  return STATUS_LABELS[status] ?? status;
}

export function formatPaymentQueueCount(count: number): string {
  return `待付款 ${count} 笔`;
}

export function formatExpenseError(detail: string | undefined): string {
  if (detail === "requester has no direct manager configured") {
    return "暂时无法提交：你的员工档案未设置直属上级。请联系管理员在「组织与员工」中补充后重试。";
  }
  return detail ?? "操作失败，请稍后重试";
}

export function expenseControls(status: string, role: string): {
  edit: boolean;
  submit: boolean;
  pay: boolean;
} {
  return {
    edit: status === "draft",
    submit: status === "draft",
    pay: status === "payment_pending" && ["finance", "admin"].includes(role),
  };
}
