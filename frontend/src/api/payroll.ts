import { apiClient } from "./client";
import type { PayrollRun, PayrollSetting } from "../types";

export async function getPayrollSettings(): Promise<PayrollSetting> {
  const response = await apiClient.get<PayrollSetting>("/admin/payroll/settings");
  return response.data;
}

export async function updatePayrollSettings(data: {
  auto_enabled: boolean;
  pay_day: number;
  generation_lead_days: number;
}): Promise<PayrollSetting> {
  const response = await apiClient.put<PayrollSetting>("/admin/payroll/settings", data);
  return response.data;
}

export async function listPayrollRuns(): Promise<PayrollRun[]> {
  const response = await apiClient.get<PayrollRun[]>("/admin/payroll/runs");
  return response.data;
}

export async function generatePayroll(period?: string): Promise<PayrollRun> {
  const response = await apiClient.post<PayrollRun>("/admin/payroll/generate", { period });
  return response.data;
}
