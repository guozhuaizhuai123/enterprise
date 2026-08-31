import { apiClient } from "./client";
import type { ExpenseAttachment, ExpenseClaim, ExpenseDraft, ExpensePayment, ExpensePreview } from "../types";
import { cancelApproval, getApproval } from "./approvals";

export async function previewExpense(text: string): Promise<ExpensePreview> {
  const response = await apiClient.post<ExpensePreview>("/expenses/preview", { text });
  return response.data;
}

export async function listExpenses(): Promise<ExpenseClaim[]> {
  const response = await apiClient.get<ExpenseClaim[]>("/expenses");
  return response.data;
}

export async function listAdminExpenses(): Promise<ExpenseClaim[]> {
  const response = await apiClient.get<ExpenseClaim[]>("/admin/expenses");
  return response.data;
}

export async function getExpense(id: string): Promise<ExpenseClaim> {
  const response = await apiClient.get<ExpenseClaim>(`/expenses/${id}`);
  return response.data;
}

export async function createExpense(data: ExpenseDraft): Promise<ExpenseClaim> {
  const response = await apiClient.post<ExpenseClaim>("/expenses", data);
  return response.data;
}

export async function updateExpense(id: string, data: ExpenseDraft): Promise<ExpenseClaim> {
  const response = await apiClient.patch<ExpenseClaim>(`/expenses/${id}`, data);
  return response.data;
}

export async function deleteExpense(id: string): Promise<void> {
  await apiClient.delete(`/expenses/${id}`);
}

export async function submitExpense(id: string): Promise<ExpenseClaim> {
  const key = `submit-${id}-${crypto.randomUUID()}`;
  const response = await apiClient.post<ExpenseClaim>(`/expenses/${id}/submit`, { idempotency_key: key });
  return response.data;
}

export async function cancelExpense(claim: ExpenseClaim, comment = "申请人撤回报销") {
  if (!claim.approval_instance_id) throw new Error("expense has no approval instance");
  const approval = await getApproval(claim.approval_instance_id);
  return cancelApproval(approval.id, approval.version, comment);
}

export async function uploadExpenseAttachment(id: string, file: File): Promise<ExpenseAttachment> {
  const form = new FormData();
  form.append("file", file);
  const response = await apiClient.post<ExpenseAttachment>(`/expenses/${id}/attachments`, form);
  return response.data;
}

export async function payExpense(
  id: string,
  data: { payment_date: string; method: string; reference: string; expected_version: number },
): Promise<ExpensePayment> {
  const response = await apiClient.post<ExpensePayment>(`/admin/expenses/${id}/pay`, {
    ...data,
    idempotency_key: `payment-${id}-${crypto.randomUUID()}`,
  });
  return response.data;
}
