import { decideAttendanceGate, shouldRefreshWorkSchedule } from "./attendanceGate.ts";
import type { AttendanceRecord } from "./types/index.ts";

function assertEqual<T>(actual: T, expected: T, message: string): void {
  if (actual !== expected) {
    throw new Error(`${message}: expected ${String(expected)}, got ${String(actual)}`);
  }
}

const todayRecord: AttendanceRecord = {
  id: "attendance-1",
  user_id: "employee-1",
  username: "alice",
  attendance_date: "2026-08-30",
  status: "present",
  note: "准时",
  recorded_by: "employee-1",
  created_at: "2026-08-30T09:00:00+08:00",
  updated_at: "2026-08-30T09:00:00+08:00",
};

assertEqual(
  decideAttendanceGate(null),
  "require-attendance",
  "missing attendance must stop the question and open check-in",
);
assertEqual(
  decideAttendanceGate(todayRecord),
  "continue",
  "existing attendance must let the question continue",
);
assertEqual(
  shouldRefreshWorkSchedule("visible"),
  true,
  "visible chat must refresh leave approval state",
);
assertEqual(
  shouldRefreshWorkSchedule("hidden"),
  false,
  "hidden chat must not poll work schedule",
);

console.log("attendanceGate tests passed");
