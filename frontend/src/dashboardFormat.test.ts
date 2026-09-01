import {
  buildDashboardExpenseHref,
  formatDashboardMoney,
  matchesExpenseDateScope,
} from "./dashboardFormat.ts";

function assertEqual(actual: unknown, expected: unknown): void {
  if (actual !== expected) throw new Error(`Expected ${expected}, got ${actual}`);
}

assertEqual(formatDashboardMoney("1234.5"), "¥1,234.50");
assertEqual(formatDashboardMoney("0"), "¥0.00");
assertEqual(formatDashboardMoney("123456789012345678.90"), "¥123,456,789,012,345,678.90");

assertEqual(
  buildDashboardExpenseHref("/admin/expenses", {
    status: "cancelled",
    start: "2026-08-01",
    end: "2026-08-31",
    departmentId: "dept/a",
  }),
  "/admin/expenses?status=cancelled&start=2026-08-01&end=2026-08-31&department=dept%2Fa",
);
assertEqual(
  buildDashboardExpenseHref("/admin/expenses", { month: "2026-08" }),
  "/admin/expenses?month=2026-08",
);

assertEqual(matchesExpenseDateScope("2026-08-15T08:00:00Z", { month: "2026-08" }), true);
assertEqual(matchesExpenseDateScope("2026-07-31T23:59:59Z", { month: "2026-08" }), false);
assertEqual(
  matchesExpenseDateScope("2026-08-15T08:00:00Z", { start: "2026-08-01", end: "2026-08-31" }),
  true,
);
assertEqual(
  matchesExpenseDateScope("2026-09-01T00:00:00Z", { start: "2026-08-01", end: "2026-08-31" }),
  false,
);

const dashboardFormat = await import("./dashboardFormat.ts");
const initialDashboardDateRange = (dashboardFormat as {
  initialDashboardDateRange?: (now: Date) => { start: string; end: string };
}).initialDashboardDateRange;
const localMorning = new Date(2026, 8, 1, 0, 30, 0);
const range = initialDashboardDateRange?.(localMorning);
if (JSON.stringify(range) !== JSON.stringify({ start: "2026-09-01", end: "2026-09-01" })) {
  throw new Error(`Expected a valid local date range, got ${JSON.stringify(range)}`);
}
