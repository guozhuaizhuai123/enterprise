import { useEffect, useState } from "react";
import { createLeaveRequest, getMyAttendanceHistory } from "../api/schedule";
import {
  formatAttendanceCoverage,
  formatAttendanceRate,
  formatAttendanceStatus,
} from "../attendanceFormat";
import LeaveRequestDialog, { type LeaveRequestPayload } from "./LeaveRequestDialog";
import { formatLeaveRange } from "../scheduleFormat";
import type { AttendanceHistory, LeavePreview } from "../types";

const LEAVE_STATUS_LABELS = {
  pending: "待审批",
  approved: "已批准",
  rejected: "已驳回",
};

export default function AttendanceHistoryDialog({
  open,
  onClose,
  refreshKey,
}: {
  open: boolean;
  onClose: () => void;
  refreshKey: number;
}) {
  const currentYear = new Date().getFullYear();
  const [year, setYear] = useState(currentYear);
  const [history, setHistory] = useState<AttendanceHistory | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [leavePreview, setLeavePreview] = useState<LeavePreview | null>(null);
  const [manualLeaveOpen, setManualLeaveOpen] = useState(false);
  const [submittingLeave, setSubmittingLeave] = useState(false);
  const [leaveError, setLeaveError] = useState("");

  async function load(selectedYear: number) {
    setLoading(true);
    setError("");
    try {
      setHistory(await getMyAttendanceHistory(selectedYear));
    } catch {
      setHistory(null);
      setError("请假与考勤历史加载失败，请稍后重试");
    } finally {
      setLoading(false);
    }
  }

  async function submitLeave(payload: LeaveRequestPayload) {
    setSubmittingLeave(true);
    setLeaveError("");
    try {
      await createLeaveRequest(payload);
      setLeavePreview(null);
      setManualLeaveOpen(false);
      await load(year);
    } catch {
      setLeaveError("请假申请提交失败，请稍后重试");
    } finally {
      setSubmittingLeave(false);
    }
  }

  useEffect(() => {
    if (open) void load(year);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, refreshKey]);

  if (!open) return null;

  const stats = history ? [
    ["累计批准请假", `${history.approved_leave_days} 天`],
    ["统一假期休息", `${history.organization_holiday_days} 天`],
    ["排班休息", `${history.weekly_rest_days} 天`],
    ["应出勤", `${history.expected_attendance_days} 天`],
    ["正常出勤", `${history.present_days} 天`],
    ["迟到", `${history.late_days} 天`],
    ["缺勤", `${history.absent_days} 天`],
    ["远程办公", `${history.remote_days} 天`],
  ] : [];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" onClick={onClose}>
      <div className="max-h-[90vh] w-full max-w-5xl overflow-y-auto rounded-xl bg-slate-50 p-6 shadow-xl" onClick={(event) => event.stopPropagation()}>
        <div className="mb-5 flex items-center justify-between">
          <div><h2 className="text-lg font-semibold text-slate-900">请假与考勤历史</h2><p className="mt-1 text-xs text-slate-400">未登记考勤不会自动算作缺勤。</p></div>
          <div className="flex items-center gap-3"><button onClick={() => { setManualLeaveOpen(true); setLeaveError(""); }} className="rounded-md bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-500">手动请假</button><select value={year} onChange={(event) => { const value = Number(event.target.value); setYear(value); void load(value); }} className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm">{Array.from({ length: 5 }, (_, index) => currentYear - index).map((value) => <option key={value} value={value}>{value} 年</option>)}</select><button onClick={onClose} className="text-sm text-slate-500 hover:text-slate-800">关闭</button></div>
        </div>

        {loading && <p className="rounded-lg bg-white p-5 text-sm text-slate-400">统计中...</p>}
        {error && <p className="rounded-lg bg-red-50 p-4 text-sm text-red-600">{error}</p>}
        {history && !loading && (
          <div className="space-y-6">
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">{stats.map(([label, value]) => <div key={label} className="rounded-lg border border-slate-200 bg-white p-4"><p className="text-xs text-slate-400">{label}</p><p className="mt-1 text-xl font-semibold text-slate-800">{value}</p></div>)}</div>
            <div className="grid gap-3 md:grid-cols-2"><div className="rounded-lg border border-slate-200 bg-white p-4"><p className="text-xs text-slate-400">考勤登记覆盖</p><p className="mt-1 font-semibold text-slate-800">{formatAttendanceCoverage(history.recorded_attendance_days, history.expected_attendance_days)}</p><p className="mt-1 text-xs text-slate-400">尚有 {history.unrecorded_attendance_days} 天未登记</p></div><div className="rounded-lg border border-slate-200 bg-white p-4"><p className="text-xs text-slate-400">已登记日期出勤率</p><p className="mt-1 font-semibold text-slate-800">{formatAttendanceRate(history.attendance_rate)}</p><p className="mt-1 text-xs text-slate-400">正常、迟到和远程办公计为出勤</p></div></div>

            <section><h3 className="mb-2 font-medium text-slate-800">请假记录</h3><div className="overflow-x-auto rounded-lg border border-slate-200 bg-white"><table className="w-full text-sm"><thead><tr className="border-b border-slate-100 text-left text-slate-400"><th className="px-4 py-3 font-medium">类型</th><th className="px-4 py-3 font-medium">日期</th><th className="px-4 py-3 font-medium">状态</th><th className="px-4 py-3 font-medium">原因</th></tr></thead><tbody>{history.leave_requests.map((item) => <tr key={item.id} className="border-b border-slate-50 last:border-0"><td className="px-4 py-3 text-slate-700">{item.leave_type}</td><td className="px-4 py-3 text-slate-600">{formatLeaveRange(item.start_date, item.end_date)}</td><td className="px-4 py-3 text-slate-600">{LEAVE_STATUS_LABELS[item.status]}</td><td className="px-4 py-3 text-slate-500">{item.reason || "-"}</td></tr>)}{history.leave_requests.length === 0 && <tr><td colSpan={4} className="px-4 py-5 text-slate-400">本年度暂无请假记录</td></tr>}</tbody></table></div></section>

            <section><h3 className="mb-2 font-medium text-slate-800">统一假期</h3><div className="rounded-lg border border-slate-200 bg-white divide-y divide-slate-100">{history.holidays.map((holiday) => <div key={holiday.id} className="flex flex-wrap justify-between gap-2 px-4 py-3 text-sm"><span className="font-medium text-slate-700">{holiday.name}</span><span className="text-slate-500">{holiday.scope_type === "company" ? "全公司" : holiday.department_name} · {formatLeaveRange(holiday.start_date, holiday.end_date)}</span></div>)}{history.holidays.length === 0 && <p className="px-4 py-5 text-sm text-slate-400">本年度暂无统一假期</p>}</div></section>

            <section><h3 className="mb-2 font-medium text-slate-800">考勤明细</h3><div className="overflow-x-auto rounded-lg border border-slate-200 bg-white"><table className="w-full text-sm"><thead><tr className="border-b border-slate-100 text-left text-slate-400"><th className="px-4 py-3 font-medium">日期</th><th className="px-4 py-3 font-medium">状态</th><th className="px-4 py-3 font-medium">备注</th></tr></thead><tbody>{history.attendance_records.map((record) => <tr key={record.id} className="border-b border-slate-50 last:border-0"><td className="px-4 py-3 text-slate-600">{record.attendance_date}</td><td className="px-4 py-3 text-slate-700">{formatAttendanceStatus(record.status)}</td><td className="px-4 py-3 text-slate-500">{record.note || "-"}</td></tr>)}{history.attendance_records.length === 0 && <tr><td colSpan={3} className="px-4 py-5 text-slate-400">本年度暂无考勤记录</td></tr>}</tbody></table></div></section>
          </div>
        )}
        <LeaveRequestDialog
          open={leavePreview !== null || manualLeaveOpen}
          preview={leavePreview}
          saving={submittingLeave}
          error={leaveError}
          onConfirm={(payload) => void submitLeave(payload)}
          onClose={() => {
            if (!submittingLeave) {
              setLeavePreview(null);
              setManualLeaveOpen(false);
              setLeaveError("");
            }
          }}
        />
      </div>
    </div>
  );
}
