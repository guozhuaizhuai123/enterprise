export function formatDashboardMoney(value: string): string {
  const [rawWhole = "0", rawFraction = ""] = value.split(".");
  const whole = rawWhole.replace(/^0+(?=\d)/, "") || "0";
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return `¥${grouped}.${(rawFraction + "00").slice(0, 2)}`;
}

function localDate(value: Date): string {
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
}

export function initialDashboardDateRange(now: Date): { start: string; end: string } {
  return {
    start: `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-01`,
    end: localDate(now),
  };
}

export interface DashboardExpenseLinkFilters {
  status?: string;
  start?: string;
  end?: string;
  month?: string;
  departmentId?: string;
}

export function buildDashboardExpenseHref(
  basePath: string,
  filters: DashboardExpenseLinkFilters,
): string {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.start) params.set("start", filters.start);
  if (filters.end) params.set("end", filters.end);
  if (filters.month) params.set("month", filters.month);
  if (filters.departmentId) params.set("department", filters.departmentId);
  const query = params.toString();
  return query ? `${basePath}?${query}` : basePath;
}

export function matchesExpenseDateScope(
  createdAt: string,
  filters: { date?: string; month?: string; start?: string; end?: string },
): boolean {
  const createdDate = createdAt.slice(0, 10);
  if (filters.date && createdDate !== filters.date) return false;
  if (filters.month && createdDate.slice(0, 7) !== filters.month) return false;
  if (filters.start && createdDate < filters.start) return false;
  if (filters.end && createdDate > filters.end) return false;
  return true;
}
