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
