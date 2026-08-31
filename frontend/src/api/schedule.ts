import { apiClient } from "./client";
import type {
  AttendanceHistory,
  AttendanceRecord,
  AttendanceStatus,
  EmployeeWorkSchedule,
  HolidayPeriod,
  HolidayScope,
  LeavePreview,
  LeaveRequest,
  MyWorkSchedule,
  ScheduleDay,
} from "../types";

export async function getMyWorkSchedule(): Promise<MyWorkSchedule> {
  const response = await apiClient.get<MyWorkSchedule>("/me/work-schedule");
  return response.data;
}

export async function getMyAttendanceHistory(year: number): Promise<AttendanceHistory> {
  const response = await apiClient.get<AttendanceHistory>("/me/attendance-history", {
    params: { year },
  });
  return response.data;
}

export async function getMyTodayAttendance(): Promise<AttendanceRecord | null> {
  const response = await apiClient.get<AttendanceRecord | null>("/me/attendance/today");
  return response.data;
}

export async function createMyTodayAttendance(data: {
  status: AttendanceStatus;
  note: string;
}): Promise<AttendanceRecord> {
  const response = await apiClient.post<AttendanceRecord>("/me/attendance/today", data);
  return response.data;
}

export async function previewLeave(text: string): Promise<LeavePreview> {
  const response = await apiClient.post<LeavePreview>("/me/leave-preview", { text });
  return response.data;
}

export async function createLeaveRequest(data: {
  leave_type: string;
  start_date: string;
  end_date: string;
  reason: string;
}): Promise<LeaveRequest> {
  const response = await apiClient.post<LeaveRequest>("/me/leave-requests", data);
  return response.data;
}

export async function listDepartmentWorkSchedules(
  departmentId: string,
): Promise<EmployeeWorkSchedule[]> {
  const response = await apiClient.get<EmployeeWorkSchedule[]>(
    `/admin/departments/${departmentId}/work-schedules`,
  );
  return response.data;
}

export async function listAllWorkSchedules(): Promise<EmployeeWorkSchedule[]> {
  const response = await apiClient.get<EmployeeWorkSchedule[]>("/admin/work-schedules");
  return response.data;
}

export async function updateEmployeeWorkSchedule(
  employeeId: string,
  days: ScheduleDay[],
): Promise<EmployeeWorkSchedule> {
  const response = await apiClient.put<EmployeeWorkSchedule>(
    `/admin/employees/${employeeId}/work-schedule`,
    { days },
  );
  return response.data;
}

export async function listDepartmentLeaveRequests(
  departmentId: string,
): Promise<LeaveRequest[]> {
  const response = await apiClient.get<LeaveRequest[]>(
    `/admin/departments/${departmentId}/leave-requests`,
  );
  return response.data;
}

export async function listAllLeaveRequests(): Promise<LeaveRequest[]> {
  const response = await apiClient.get<LeaveRequest[]>("/admin/leave-requests");
  return response.data;
}

export async function reviewLeaveRequest(
  requestId: string,
  status: "approved" | "rejected",
): Promise<LeaveRequest> {
  const response = await apiClient.patch<LeaveRequest>(
    `/admin/leave-requests/${requestId}`,
    { status },
  );
  return response.data;
}

export async function listHolidays(departmentId?: string): Promise<HolidayPeriod[]> {
  const response = await apiClient.get<HolidayPeriod[]>("/admin/holidays", {
    params: departmentId ? { department_id: departmentId } : undefined,
  });
  return response.data;
}

export async function createHoliday(data: {
  name: string;
  scope_type: HolidayScope;
  department_id: string | null;
  start_date: string;
  end_date: string;
  description: string;
}): Promise<HolidayPeriod> {
  const response = await apiClient.post<HolidayPeriod>("/admin/holidays", data);
  return response.data;
}

export async function deleteHoliday(holidayId: string): Promise<void> {
  await apiClient.delete(`/admin/holidays/${holidayId}`);
}

export async function listAttendance(
  year: number,
  departmentId?: string,
): Promise<AttendanceRecord[]> {
  const response = await apiClient.get<AttendanceRecord[]>("/admin/attendance", {
    params: { year, ...(departmentId ? { department_id: departmentId } : {}) },
  });
  return response.data;
}

export async function saveAttendance(
  employeeId: string,
  attendanceDate: string,
  data: { status: AttendanceStatus; note: string },
): Promise<AttendanceRecord> {
  const response = await apiClient.put<AttendanceRecord>(
    `/admin/employees/${employeeId}/attendance/${attendanceDate}`,
    data,
  );
  return response.data;
}

export async function deleteAttendance(
  employeeId: string,
  attendanceDate: string,
): Promise<void> {
  await apiClient.delete(`/admin/employees/${employeeId}/attendance/${attendanceDate}`);
}
