import { useState } from "react";
import { formatAttendanceStatus } from "../attendanceFormat";
import type { AttendanceStatus } from "../types";

const STATUS_OPTIONS: AttendanceStatus[] = ["present", "late", "remote", "absent"];

interface Props {
  saving: boolean;
  error: string;
  onConfirm: (status: AttendanceStatus, note: string) => void;
  onClose: () => void;
  mode?: "question" | "login";
}

export default function AttendanceCheckinDialog({ saving, error, onConfirm, onClose, mode = "question" }: Props) {
  const [status, setStatus] = useState<AttendanceStatus>("present");
  const [note, setNote] = useState("");

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/35 p-4">
      <div role="dialog" aria-modal="true" aria-labelledby="attendance-checkin-title" className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-5 shadow-xl">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 id="attendance-checkin-title" className="text-lg font-semibold text-slate-900">今日打卡</h2>
            <p className="mt-1 text-sm text-slate-500">
              {mode === "question"
                ? "今天尚未登记考勤，完成后将自动继续发送你的问题。"
                : "今天尚未登记考勤，请选择今日出勤状态。"}
            </p>
          </div>
          <button type="button" onClick={onClose} disabled={saving} aria-label="关闭今日打卡" className="rounded px-2 py-1 text-slate-400 hover:bg-slate-50 disabled:opacity-50">×</button>
        </div>

        {error && <p className="mt-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>}

        <div className="mt-4 space-y-4">
          <label className="block text-sm text-slate-600">
            考勤状态
            <select value={status} onChange={(event) => setStatus(event.target.value as AttendanceStatus)} className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm">
              {STATUS_OPTIONS.map((item) => <option key={item} value={item}>{formatAttendanceStatus(item)}</option>)}
            </select>
          </label>
          <label className="block text-sm text-slate-600">
            备注（可选）
            <textarea value={note} onChange={(event) => setNote(event.target.value)} maxLength={300} rows={3} placeholder="例如：居家办公、交通延误" className="mt-1 block w-full resize-none rounded-md border border-slate-300 px-3 py-2 text-sm" />
          </label>
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <button type="button" onClick={onClose} disabled={saving} className="rounded-md border border-slate-300 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-50">暂不打卡</button>
          <button type="button" onClick={() => onConfirm(status, note.trim())} disabled={saving} className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-60">{saving ? "提交中..." : mode === "question" ? "确认打卡并继续" : "确认打卡"}</button>
        </div>
      </div>
    </div>
  );
}
