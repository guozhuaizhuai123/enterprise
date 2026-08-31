import {
  approvalConfirmation,
  approvalProgressModel,
  approvalRouteSummary,
  defaultApprovalSelection,
  formatApprovalAction,
  formatApprovalCounts,
  formatApprovalStatus,
} from "./approvalFormat.ts";
import type { ApprovalRouteStep } from "./types/index.ts";

function assertEqual(actual: unknown, expected: unknown): void {
  if (actual !== expected) throw new Error(`Expected ${expected}, got ${actual}`);
}

function assertDeepEqual(actual: unknown, expected: unknown): void {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(`Expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}

assertEqual(formatApprovalStatus("pending_approval"), "审批中");
assertEqual(formatApprovalStatus("approved"), "已通过");
assertEqual(formatApprovalStatus("rejected"), "已驳回");
assertEqual(formatApprovalStatus("cancelled"), "已撤回");
assertEqual(formatApprovalAction("submit"), "提交申请");
assertEqual(formatApprovalAction("approve"), "审批通过");
assertEqual(formatApprovalAction("reject"), "驳回申请");
assertEqual(formatApprovalAction("cancel"), "撤回申请");
assertDeepEqual(approvalConfirmation("approve", "同意报销"), {
  action: "approve",
  comment: "同意报销",
  title: "确认通过这项申请？",
  confirmLabel: "确认通过",
});

assertEqual(formatApprovalCounts(1, 2), "待我审批 1 · 我发起 2");
assertEqual(defaultApprovalSelection(null, "inbox", ["task-1"], ["submitted-1"]), "task-1");
assertEqual(defaultApprovalSelection(null, "submitted", ["task-1"], ["submitted-1"]), "submitted-1");
assertEqual(defaultApprovalSelection("selected", "inbox", ["task-1"], []), null);
// 审批历史不自动选中，避免一进页面就多发一次详情请求
assertEqual(defaultApprovalSelection(null, "history", ["task-1"], ["submitted-1"]), null);

const route: ApprovalRouteStep[] = [
  { sequence: 0, name: "提交申请", status: "approved", handlers: [{ id: "u1", username: "gjk", display_name: "gjk" }] },
  { sequence: 1, name: "直属上级审批", status: "pending", handlers: [{ id: "u2", username: "legal", display_name: "法务负责人" }] },
  { sequence: 2, name: "财务复核", status: "upcoming", handlers: [{ id: "u3", username: "finance", display_name: "财务负责人" }] },
  { sequence: 3, name: "财务付款", status: "upcoming", handlers: [{ id: "u3", username: "finance", display_name: "财务负责人" }] },
];
assertDeepEqual(approvalRouteSummary(route), {
  current: "法务负责人（legal）",
  next: "财务负责人（finance）",
  final: "财务负责人（finance）",
});
assertDeepEqual(approvalRouteSummary(undefined), {
  current: "暂未配置处理人",
  next: "",
  final: "暂未配置处理人",
});

assertEqual(
  approvalProgressModel("approved", [
    { sequence: 0, name: "提交申请", status: "approved", handlers: [] },
    { sequence: 1, name: "财务付款", status: "pending", handlers: [{ id: "u3", username: "finance", display_name: "财务负责人" }] },
  ], "payment_pending").outcome,
  "审批已通过，待付款",
);
assertEqual(
  approvalProgressModel("approved", [
    { sequence: 0, name: "提交申请", status: "approved", handlers: [] },
    { sequence: 1, name: "财务付款", status: "approved", handlers: [] },
  ], "paid").outcome,
  "已付款",
);
const pendingModel = approvalProgressModel("pending_approval", route);
assertEqual(pendingModel.current?.name, "直属上级审批");
assertEqual(pendingModel.upcoming.length, 2);
