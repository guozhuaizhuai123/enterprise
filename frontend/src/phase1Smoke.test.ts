import { notificationTarget, phase1Routes } from "./phase1Navigation.ts";

function assert(condition: boolean, message: string): void {
  if (!condition) throw new Error(message);
}

for (const route of ["/admin/organization", "/admin/approvals", "/admin/expenses", "/admin/dashboard", "/approvals", "/expenses"]) {
  assert(phase1Routes.includes(route as never), `Missing phase-one route: ${route}`);
}

const base = {
  id: "n1",
  ticket_id: null,
  todo_id: null,
  kind: "approval_assigned",
  content: "待审批",
  read_at: null,
  created_at: "2026-08-30T00:00:00Z",
};
assert(notificationTarget({ ...base, approval_instance_id: "a/1", expense_claim_id: null }) === "/approvals?approval=a%2F1", "Approval notification target mismatch");
assert(notificationTarget({ ...base, approval_instance_id: null, expense_claim_id: "e/1" }) === "/expenses?expense=e%2F1", "Expense notification target mismatch");
