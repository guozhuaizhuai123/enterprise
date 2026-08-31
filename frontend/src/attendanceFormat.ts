import type { AttendanceStatus, HolidayPeriod } from "./types/index.ts";

const ATTENDANCE_LABELS: Record<AttendanceStatus, string> = {
  present: "正常出勤",
  late: "迟到",
  absent: "缺勤",
  remote: "远程办公",
};

export function formatHolidayScope(
  holiday: HolidayPeriod,
  departments: Array<{ id: string; name: string }>,
): string {
  if (holiday.scope_type === "company") return "全公司";
  return (
    holiday.department_name ||
    departments.find((department) => department.id === holiday.department_id)?.name ||
    "部门"
  );
}

export function formatAttendanceStatus(status: AttendanceStatus): string {
  return ATTENDANCE_LABELS[status];
}

export function formatAttendanceRate(rate: number | null): string {
  if (rate === null) return "暂无考勤数据";
  return `${Number((rate * 100).toFixed(1))}%`;
}

export function formatAttendanceCoverage(recorded: number, expected: number): string {
  if (expected === 0) return `${recorded}/${expected} 天（0%）`;
  return `${recorded}/${expected} 天（${Number(((recorded / expected) * 100).toFixed(1))}%）`;
}
