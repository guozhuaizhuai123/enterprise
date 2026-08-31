import {
  formatAttendanceCoverage,
  formatAttendanceRate,
  formatAttendanceStatus,
  formatHolidayScope,
} from "./attendanceFormat.ts";

function assertEqual(actual: unknown, expected: unknown): void {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(`Expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}

const departments = [
  { id: "dept-1", name: "法务部", created_at: "2026-01-01T00:00:00Z" },
];
const companyHoliday = {
  id: "holiday-1",
  name: "国庆节",
  scope_type: "company" as const,
  department_id: null,
  department_name: "",
  start_date: "2026-10-01",
  end_date: "2026-10-07",
  description: "",
  created_by: "admin-1",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};
const departmentHoliday = {
  ...companyHoliday,
  id: "holiday-2",
  scope_type: "department" as const,
  department_id: "dept-1",
  department_name: "法务部",
};

assertEqual(formatHolidayScope(companyHoliday, departments), "全公司");
assertEqual(formatHolidayScope(departmentHoliday, departments), "法务部");
assertEqual(formatAttendanceStatus("present"), "正常出勤");
assertEqual(formatAttendanceStatus("remote"), "远程办公");
assertEqual(formatAttendanceRate(null), "暂无考勤数据");
assertEqual(formatAttendanceRate(0.875), "87.5%");
assertEqual(formatAttendanceCoverage(8, 10), "8/10 天（80%）");

console.log("attendanceFormat tests passed");
