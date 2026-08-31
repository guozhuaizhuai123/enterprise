import { apiClient } from "./client";
import type { DashboardOverview } from "../types";

export interface DashboardFilters {
  start?: string;
  end?: string;
  departmentId?: string;
}

function params(filters?: DashboardFilters) {
  return {
    start: filters?.start || undefined,
    end: filters?.end || undefined,
    department_id: filters?.departmentId || undefined,
  };
}

export async function getDashboardOverview(filters?: DashboardFilters): Promise<DashboardOverview> {
  const response = await apiClient.get<DashboardOverview>("/admin/dashboard/overview", { params: params(filters) });
  return response.data;
}

export async function getDashboardExpenses(filters?: DashboardFilters) {
  const response = await apiClient.get<Pick<DashboardOverview, "period_start" | "period_end" | "timezone" | "expenses" | "monthly_expenses">>("/admin/dashboard/expenses", { params: params(filters) });
  return response.data;
}

export async function getDashboardApprovals(filters?: DashboardFilters) {
  const response = await apiClient.get<Pick<DashboardOverview, "period_start" | "period_end" | "timezone" | "approvals">>("/admin/dashboard/approvals", { params: params(filters) });
  return response.data;
}
