import { useEffect, useState } from "react";
import { listDepartments } from "../api/admin";
import {
  deleteAttendance,
  listAllWorkSchedules,
  listAttendance,
  listDepartmentWorkSchedules,
  saveAttendance,
} from "../api/schedule";
import { formatAttendanceStatus } from "../attendanceFormat";
import { shouldRefreshWorkSchedule } from "../attendanceGate";
import type { AttendanceRecord, AttendanceStatus, Department, EmployeeWorkSchedule } from "../types";

function todayValue(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

const STATUS_OPTIONS: AttendanceStatus[] = ["present", "late", "absent", "remote"];

export default function AttendanceManagement({ departmentId }: { departmentId?: string }) {
  const currentYear = new Date().getFullYear();
  const [selectedDepartmentId, setSelectedDepartmentId] = useState(departmentId ?? "");
  const [departments, setDepartments] = useState<Department[]>([]);
  const [employees, setEmployees] = useState<EmployeeWorkSchedule[]>([]);
  const [records, setRecords] = useState<AttendanceRecord[]>([]);
  const [employeeId, setEmployeeId] = useState("");
  const [attendanceDate, setAttendanceDate] = useState(todayValue());
  const [attendanceStatus, setAttendanceStatus] = useState<AttendanceStatus>("present");
  const [note, setNote] = useState("");
  const [year, setYear] = useState(currentYear);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function refresh(scopeId = selectedDepartmentId, selectedYear = year) {
    setLoading(true);
    setError("");
    try {
      const [departmentRows, employeeRows, attendanceRows] = await Promise.all([
        listDepartments(),
        scopeId ? listDepartmentWorkSchedules(scopeId) : listAllWorkSchedules(),
        listAttendance(selectedYear, scopeId || undefined),
      ]);
      setDepartments(departmentRows);
      setEmployees(employeeRows);
      setRecords(attendanceRows);
      setEmployeeId((current) => employeeRows.some((item) => item.user_id === current) ? current : (employeeRows[0]?.user_id ?? ""));
    } catch {
      setError("考勤数据加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const scopeId = departmentId ?? "";
    setSelectedDepartmentId(scopeId);
    void refresh(scopeId, year);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [departmentId]);

  useEffect(() => {
    const refreshRecords = () => {
      if (!shouldRefreshWorkSchedule(document.visibilityState)) return;
      listAttendance(year, selectedDepartmentId || undefined).then(setRecords).catch(() => {});
    };
    const intervalId = window.setInterval(refreshRecords, 5000);
    window.addEventListener("focus", refreshRecords);
    document.addEventListener("visibilitychange", refreshRecords);
    return () => {
      window.clearInterval(intervalId);
      window.removeEventListener("focus", refreshRecords);
      document.removeEventListener("visibilitychange", refreshRecords);
    };
  }, [selectedDepartmentId, year]);

  async function changeDepartment(value: string) {
    setSelectedDepartmentId(value);
    await refresh(value, year);
  }

  async function changeYear(value: number) {
    setYear(value);
    await refresh(selectedDepartmentId, value);
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!employeeId || !attendanceDate) return;
    setSaving(true);
    setError("");
    try {
      await saveAttendance(employeeId, attendanceDate, { status: attendanceStatus, note: note.trim() });
      setNote("");
      await refresh();
    } catch {
      setError("考勤保存失败，不能登记未来日期");
    } finally {
      setSaving(false);
    }
  }

  async function remove(record: AttendanceRecord) {
    if (!confirm(`确定删除 ${record.username} 在 ${record.attendance_date} 的考勤？该记录会从数据库中删除。`)) return;
    setError("");
    try {
      await deleteAttendance(record.user_id, record.attendance_date);
      await refresh();
    } catch {
      setError("删除失败，原考勤记录已保留");
    }
  }

  return (
    <section>
      <div className="mb-3">
        <h3 className="font-medium text-slate-800">考勤登记</h3>
        <p className="mt-1 text-xs text-slate-400">人工登记正常、迟到、缺勤或远程办公；未登记不会自动判定缺勤。</p>
      </div>
      {error && <p className="mb-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>}
      <form onSubmit={submit} className="mb-4 flex flex-wrap items-end gap-3 rounded-lg border border-slate-200 bg-white p-4">
        {!departmentId && <label className="text-xs text-slate-500">部门筛选<select className="mt-1 block rounded-md border border-slate-300 px-3 py-2 text-sm" value={selectedDepartmentId} onChange={(event) => void changeDepartment(event.target.value)}><option value="">全部部门</option>{departments.map((department) => <option key={department.id} value={department.id}>{department.name}</option>)}</select></label>}
        <label className="text-xs text-slate-500">员工<select className="mt-1 block min-w-36 rounded-md border border-slate-300 px-3 py-2 text-sm" value={employeeId} onChange={(event) => setEmployeeId(event.target.value)}><option value="">选择员工</option>{employees.map((employee) => <option key={employee.user_id} value={employee.user_id}>{employee.username}</option>)}</select></label>
        <label className="text-xs text-slate-500">日期<input type="date" max={todayValue()} className="mt-1 block rounded-md border border-slate-300 px-3 py-2 text-sm" value={attendanceDate} onChange={(event) => setAttendanceDate(event.target.value)} /></label>
        <label className="text-xs text-slate-500">状态<select className="mt-1 block rounded-md border border-slate-300 px-3 py-2 text-sm" value={attendanceStatus} onChange={(event) => setAttendanceStatus(event.target.value as AttendanceStatus)}>{STATUS_OPTIONS.map((status) => <option key={status} value={status}>{formatAttendanceStatus(status)}</option>)}</select></label>
        <input className="min-w-48 flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm" placeholder="备注（可选）" value={note} onChange={(event) => setNote(event.target.value)} />
        <button disabled={saving || !employeeId} className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60">{saving ? "保存中..." : "保存考勤"}</button>
      </form>

      <div className="mb-2 flex justify-end"><select value={year} onChange={(event) => void changeYear(Number(event.target.value))} className="rounded-md border border-slate-300 px-3 py-1.5 text-sm">{Array.from({ length: 5 }, (_, index) => currentYear - index).map((value) => <option key={value} value={value}>{value} 年</option>)}</select></div>
      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <table className="w-full text-sm"><thead><tr className="border-b border-slate-100 text-left text-slate-400"><th className="px-4 py-3 font-medium">日期</th><th className="px-4 py-3 font-medium">员工</th><th className="px-4 py-3 font-medium">状态</th><th className="px-4 py-3 font-medium">来源</th><th className="px-4 py-3 font-medium">备注</th><th className="px-4 py-3 font-medium" /></tr></thead>
          <tbody>{records.map((record) => <tr key={record.id} className="border-b border-slate-50 last:border-0"><td className="px-4 py-3 text-slate-600">{record.attendance_date}</td><td className="px-4 py-3 font-medium text-slate-800">{record.username}</td><td className="px-4 py-3 text-slate-600">{formatAttendanceStatus(record.status)}</td><td className="px-4 py-3 text-slate-500">{record.recorded_by === record.user_id ? "员工打卡" : "管理员核定"}</td><td className="px-4 py-3 text-slate-500">{record.note || "-"}</td><td className="px-4 py-3 text-right"><button onClick={() => void remove(record)} className="text-xs text-red-500 hover:text-red-700">删除</button></td></tr>)}{!loading && records.length === 0 && <tr><td colSpan={6} className="px-4 py-5 text-slate-400">暂无考勤记录</td></tr>}{loading && <tr><td colSpan={6} className="px-4 py-5 text-slate-400">加载中...</td></tr>}</tbody>
        </table>
      </div>
    </section>
  );
}
