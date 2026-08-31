import type { AttendanceRecord } from "./types/index.ts";

export type AttendanceGateDecision = "continue" | "require-attendance";

export function decideAttendanceGate(
  attendance: AttendanceRecord | null,
): AttendanceGateDecision {
  return attendance === null ? "require-attendance" : "continue";
}

export function shouldRefreshWorkSchedule(visibilityState: string): boolean {
  return visibilityState === "visible";
}
