import { expenseControls, formatExpenseError, formatExpenseStatus, formatPaymentQueueCount, sumExpenseAmounts } from "./expenseFormat.ts";

function assertEqual(actual: unknown, expected: unknown): void {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(`Expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}

assertEqual(sumExpenseAmounts(["12.30", "7.70"]), "20.00");
assertEqual(sumExpenseAmounts(["0.105", "0.105"]), "0.22");
assertEqual(sumExpenseAmounts(["", "abc", "-1"]), null);
assertEqual(formatExpenseStatus("draft"), "草稿");
assertEqual(formatExpenseStatus("pending_approval"), "审批中");
assertEqual(formatExpenseStatus("payment_pending"), "待付款");
assertEqual(formatExpenseStatus("paid"), "已付款");
assertEqual(expenseControls("draft", "employee"), { edit: true, submit: true, pay: false });
assertEqual(expenseControls("payment_pending", "finance"), { edit: false, submit: false, pay: true });
assertEqual(expenseControls("payment_pending", "manager"), { edit: false, submit: false, pay: false });
assertEqual(formatPaymentQueueCount(0), "待付款 0 笔");
assertEqual(
  formatExpenseError("requester has no direct manager configured"),
  "暂时无法提交：你的员工档案未设置直属上级。请联系管理员在「组织与员工」中补充后重试。",
);
