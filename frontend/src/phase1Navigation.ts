import type { Notification } from "./types";

export const phase1Routes = [
  "/admin/organization",
  "/admin/approvals",
  "/admin/expenses",
  "/admin/dashboard",
  "/approvals",
  "/expenses",
  "/applications",
  "/organization",
] as const;

export function notificationTarget(notification: Notification): string | null {
  if (notification.approval_instance_id) {
    return `/approvals?approval=${encodeURIComponent(notification.approval_instance_id)}`;
  }
  if (notification.expense_claim_id) {
    return `/expenses?expense=${encodeURIComponent(notification.expense_claim_id)}`;
  }
  return null;
}
