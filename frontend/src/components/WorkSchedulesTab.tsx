import { useEffect, useState } from "react";
import {
  listAllLeaveRequests,
  listAllWorkSchedules,
  listDepartmentLeaveRequests,
  listDepartmentWorkSchedules,
  reviewLeaveRequest,
  updateEmployeeWorkSchedule,
} from "../api/schedule";
import { formatLeaveRange, formatWeeklySchedule, WEEKDAY_LABELS } from "../scheduleFormat";
import type { EmployeeWorkSchedule, LeaveRequest, ScheduleDay } from "../types";
import AttendanceManagement from "./AttendanceManagement";
import HolidayManagement from "./HolidayManagement";

const STATUS_LABELS = { pending: "待审批", approved: "已批准", rejected: "已驳回" };

export default function WorkSchedulesTab({ departmentId }: { departmentId?: string }) {
  const [schedules, setSchedules] = useState<EmployeeWorkSchedule[]>([]);
  const [requests, setRequests] = useState<LeaveRequest[]>([]);
  const [editing, setEditing] = useState<EmployeeWorkSchedule | null>(null);
  const [editingDays, setEditingDays] = useState<ScheduleDay[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function refresh() {
    setLoading(true);
    setError("");
    try {
      const [scheduleRows, leaveRows] = await Promise.all(
        departmentId
          ? [listDepartmentWorkSchedules(departmentId), listDepartmentLeaveRequests(departmentId)]
          : [listAllWorkSchedules(), listAllLeaveRequests()],
      );
      setSchedules(scheduleRows);
      setRequests(leaveRows);
    } catch {
      setError("上班安排加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [departmentId]);

  function beginEdit(row: EmployeeWorkSchedule) {
    setEditing(row);
    setEditingDays(row.days.map((day) => ({ ...day })));
    setError("");
  }

  function updateDay(weekday: number, values: Partial<ScheduleDay>) {
    setEditingDays((current) =>
      current.map((day) => (day.weekday === weekday ? { ...day, ...values } : day)),
    );
  }

  async function saveSchedule() {
    if (!editing) return;
    const workingDays = editingDays.filter((day) => day.enabled);
    if (workingDays.length === 0 || workingDays.some((day) => day.start_time >= day.end_time)) {
      setError("至少选择一个工作日，并确保上班时间早于下班时间");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await updateEmployeeWorkSchedule(editing.user_id, editingDays);
      setEditing(null);
      await refresh();
    } catch {
      setError("上班安排保存失败");
    } finally {
      setSaving(false);
    }
  }

  async function review(item: LeaveRequest, status: "approved" | "rejected") {
    setError("");
    try {
      await reviewLeaveRequest(item.id, status);
      await refresh();
    } catch {
      setError("审批失败，该申请可能已被处理");
    }
  }

  if (loading) return <p className="text-sm text-slate-400">加载上班安排...</p>;

  return (
    <div className="space-y-8">
      {error && <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>}

      <HolidayManagement departmentId={departmentId} />

      <AttendanceManagement departmentId={departmentId} />

      <section>
        <div className="mb-3">
          <h3 className="font-medium text-slate-800">员工上班周期</h3>
          <p className="mt-1 text-xs text-slate-400">设置每周工作日和每日上下班时间。</p>
        </div>
        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 text-left text-slate-400">
                <th className="px-4 py-3 font-medium">员工</th>
                <th className="px-4 py-3 font-medium">当前上班安排</th>
                <th className="px-4 py-3 font-medium" />
              </tr>
            </thead>
            <tbody>
              {schedules.map((row) => (
                <tr key={row.user_id} className="border-b border-slate-50 last:border-0">
                  <td className="px-4 py-3 font-medium text-slate-800">{row.username}</td>
                  <td className="px-4 py-3 text-slate-600">{formatWeeklySchedule(row.days)}</td>
                  <td className="px-4 py-3 text-right">
                    <button onClick={() => beginEdit(row)} className="text-xs text-indigo-600 hover:text-indigo-800">
                      设置
                    </button>
                  </td>
                </tr>
              ))}
              {schedules.length === 0 && (
                <tr><td colSpan={3} className="px-4 py-5 text-slate-400">该部门暂无员工</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <div className="mb-3">
          <h3 className="font-medium text-slate-800">请假审批</h3>
          <p className="mt-1 text-xs text-slate-400">批准后自动同步到员工的上班安排。</p>
        </div>
        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 text-left text-slate-400">
                <th className="px-4 py-3 font-medium">员工</th>
                <th className="px-4 py-3 font-medium">类型</th>
                <th className="px-4 py-3 font-medium">日期</th>
                <th className="px-4 py-3 font-medium">原因</th>
                <th className="px-4 py-3 font-medium">状态</th>
                <th className="px-4 py-3 font-medium" />
              </tr>
            </thead>
            <tbody>
              {requests.map((item) => (
                <tr key={item.id} className="border-b border-slate-50 last:border-0 align-top">
                  <td className="px-4 py-3 font-medium text-slate-800">{item.username}</td>
                  <td className="px-4 py-3 text-slate-600">{item.leave_type}</td>
                  <td className="px-4 py-3 whitespace-nowrap text-slate-600">{formatLeaveRange(item.start_date, item.end_date)}</td>
                  <td className="max-w-64 px-4 py-3 text-slate-500">{item.reason || "-"}</td>
                  <td className="px-4 py-3 text-slate-500">{STATUS_LABELS[item.status]}</td>
                  <td className="px-4 py-3 text-right whitespace-nowrap">
                    {item.status === "pending" && (
                      <>
                        <button onClick={() => void review(item, "approved")} className="mr-3 text-xs text-emerald-600 hover:text-emerald-800">批准</button>
                        <button onClick={() => void review(item, "rejected")} className="text-xs text-red-500 hover:text-red-700">驳回</button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
              {requests.length === 0 && (
                <tr><td colSpan={6} className="px-4 py-5 text-slate-400">暂无请假申请</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {editing && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={() => !saving && setEditing(null)}>
          <div className="w-full max-w-xl rounded-xl bg-white p-6 shadow-xl" onClick={(event) => event.stopPropagation()}>
            <h3 className="font-semibold text-slate-900">设置 {editing.username} 的上班周期</h3>
            <div className="mt-4 divide-y divide-slate-100">
              {editingDays.map((day) => (
                <div key={day.weekday} className="flex items-center gap-3 py-2.5">
                  <label className="flex w-24 items-center gap-2 text-sm text-slate-700">
                    <input type="checkbox" checked={day.enabled} onChange={(event) => updateDay(day.weekday, { enabled: event.target.checked })} />
                    {WEEKDAY_LABELS[day.weekday - 1]}
                  </label>
                  <input type="time" disabled={!day.enabled} value={day.start_time} onChange={(event) => updateDay(day.weekday, { start_time: event.target.value })} className="rounded border border-slate-300 px-2 py-1.5 text-sm disabled:bg-slate-50" />
                  <span className="text-slate-400">至</span>
                  <input type="time" disabled={!day.enabled} value={day.end_time} onChange={(event) => updateDay(day.weekday, { end_time: event.target.value })} className="rounded border border-slate-300 px-2 py-1.5 text-sm disabled:bg-slate-50" />
                </div>
              ))}
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button disabled={saving} onClick={() => setEditing(null)} className="px-4 py-2 text-sm text-slate-500">取消</button>
              <button disabled={saving} onClick={() => void saveSchedule()} className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60">{saving ? "保存中..." : "保存"}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
