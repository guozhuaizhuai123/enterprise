import { useEffect, useState } from "react";
import { LEAVE_TYPES } from "../scheduleFormat";
import type { LeavePreview } from "../types";

export interface LeaveRequestPayload {
  leave_type: string;
  start_date: string;
  end_date: string;
  reason: string;
}

export default function LeaveRequestDialog({
  open,
  preview,
  saving,
  error,
  onConfirm,
  onClose,
}: {
  open: boolean;
  preview: LeavePreview | null;
  saving: boolean;
  error: string;
  onConfirm: (payload: LeaveRequestPayload) => void;
  onClose: () => void;
}) {
  const [leaveType, setLeaveType] = useState("其他");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [reason, setReason] = useState("");
  const [validation, setValidation] = useState("");

  useEffect(() => {
    if (!open) return;
    if (preview) {
      setLeaveType(preview.leave_type || "其他");
      setStartDate(preview.start_date || "");
      setEndDate(preview.end_date || preview.start_date || "");
      setReason(preview.reason || "");
    } else {
      setLeaveType("其他");
      setStartDate("");
      setEndDate("");
      setReason("");
    }
    setValidation("");
  }, [open, preview]);

  function submit() {
    if (!startDate || !endDate) {
      setValidation("请选择请假的开始和结束日期");
      return;
    }
    if (startDate > endDate) {
      setValidation("开始日期不能晚于结束日期");
      return;
    }
    setValidation("");
    onConfirm({ leave_type: leaveType, start_date: startDate, end_date: endDate, reason: reason.trim() });
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30" onClick={() => !saving && onClose()}>
      <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl" onClick={(event) => event.stopPropagation()}>
        <h3 className="font-semibold text-slate-900">{preview ? "确认请假申请" : "新建请假申请"}</h3>
        <p className="mt-1 text-xs text-slate-400">提交后等待管理员审批，批准后自动同步上班安排。</p>
        <div className="mt-5 space-y-4">
          <label className="block text-sm text-slate-600">
            <span className="mb-1 block">请假类型</span>
            <select value={leaveType} onChange={(event) => setLeaveType(event.target.value)} className="w-full rounded-md border border-slate-300 px-3 py-2">
              {LEAVE_TYPES.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>
          <div className="grid grid-cols-2 gap-3">
            <label className="block text-sm text-slate-600">
              <span className="mb-1 block">开始日期</span>
              <input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} className="w-full rounded-md border border-slate-300 px-3 py-2" />
            </label>
            <label className="block text-sm text-slate-600">
              <span className="mb-1 block">结束日期</span>
              <input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} className="w-full rounded-md border border-slate-300 px-3 py-2" />
            </label>
          </div>
          <label className="block text-sm text-slate-600">
            <span className="mb-1 block">请假原因</span>
            <textarea value={reason} onChange={(event) => setReason(event.target.value)} maxLength={300} className="h-24 w-full resize-none rounded-md border border-slate-300 px-3 py-2" />
          </label>
        </div>
        {(validation || error) && <p className="mt-3 text-sm text-red-600">{validation || error}</p>}
        <div className="mt-5 flex justify-end gap-2">
          <button disabled={saving} onClick={onClose} className="px-4 py-2 text-sm text-slate-500 disabled:opacity-50">取消</button>
          <button disabled={saving} onClick={submit} className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60">{saving ? "提交中..." : "确认提交"}</button>
        </div>
      </div>
    </div>
  );
}
