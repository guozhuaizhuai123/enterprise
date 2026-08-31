import { useEffect, useState } from "react";
import { listDepartments } from "../api/admin";
import { createHoliday, deleteHoliday, listHolidays } from "../api/schedule";
import { formatHolidayScope } from "../attendanceFormat";
import { formatLeaveRange } from "../scheduleFormat";
import type { Department, HolidayPeriod, HolidayScope } from "../types";

function localDate(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

export default function HolidayManagement({ departmentId }: { departmentId?: string }) {
  const [holidays, setHolidays] = useState<HolidayPeriod[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [name, setName] = useState("");
  const [scopeType, setScopeType] = useState<HolidayScope>(departmentId ? "department" : "company");
  const [selectedDepartmentId, setSelectedDepartmentId] = useState(departmentId ?? "");
  const [startDate, setStartDate] = useState(localDate());
  const [endDate, setEndDate] = useState(localDate());
  const [description, setDescription] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function refresh() {
    setLoading(true);
    setError("");
    try {
      const [holidayRows, departmentRows] = await Promise.all([
        listHolidays(departmentId),
        listDepartments(),
      ]);
      setHolidays(holidayRows);
      setDepartments(departmentRows);
      if (!departmentId && !selectedDepartmentId && departmentRows[0]) {
        setSelectedDepartmentId(departmentRows[0].id);
      }
    } catch {
      setError("统一假期加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    setScopeType(departmentId ? "department" : "company");
    setSelectedDepartmentId(departmentId ?? "");
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [departmentId]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!name.trim() || !startDate || !endDate) return;
    if (startDate > endDate) {
      setError("假期开始日期不能晚于结束日期");
      return;
    }
    if (scopeType === "department" && !selectedDepartmentId) {
      setError("请选择放假的部门");
      return;
    }
    setSaving(true);
    setError("");
    try {
      await createHoliday({
        name: name.trim(),
        scope_type: scopeType,
        department_id: scopeType === "department" ? selectedDepartmentId : null,
        start_date: startDate,
        end_date: endDate,
        description: description.trim(),
      });
      setName("");
      setDescription("");
      await refresh();
    } catch {
      setError("保存失败，请检查日期、范围，或是否存在完全相同的假期");
    } finally {
      setSaving(false);
    }
  }

  async function remove(holiday: HolidayPeriod) {
    if (!confirm(`确定删除统一假期“${holiday.name}”？该记录会从数据库中删除。`)) return;
    setError("");
    try {
      await deleteHoliday(holiday.id);
      await refresh();
    } catch {
      setError("删除失败，原记录已保留");
    }
  }

  return (
    <section>
      <div className="mb-3">
        <h3 className="font-medium text-slate-800">统一假期</h3>
        <p className="mt-1 text-xs text-slate-400">设置全公司或部门统一休假；过期后员工端自动隐藏，历史记录继续保留。</p>
      </div>
      {error && <p className="mb-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>}
      <form onSubmit={submit} className="mb-4 grid gap-3 rounded-lg border border-slate-200 bg-white p-4 md:grid-cols-6">
        <input className="rounded-md border border-slate-300 px-3 py-2 text-sm md:col-span-2" placeholder="假期名称，如国庆节" value={name} onChange={(event) => setName(event.target.value)} />
        {!departmentId && (
          <select className="rounded-md border border-slate-300 px-3 py-2 text-sm" value={scopeType} onChange={(event) => setScopeType(event.target.value as HolidayScope)}>
            <option value="company">全公司</option>
            <option value="department">指定部门</option>
          </select>
        )}
        {scopeType === "department" && (
          <select disabled={Boolean(departmentId)} className="rounded-md border border-slate-300 px-3 py-2 text-sm disabled:bg-slate-50" value={selectedDepartmentId} onChange={(event) => setSelectedDepartmentId(event.target.value)}>
            <option value="">选择部门</option>
            {departments.map((department) => <option key={department.id} value={department.id}>{department.name}</option>)}
          </select>
        )}
        <label className="text-xs text-slate-500">开始日期<input type="date" className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm" value={startDate} onChange={(event) => setStartDate(event.target.value)} /></label>
        <label className="text-xs text-slate-500">结束日期<input type="date" className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-sm" value={endDate} onChange={(event) => setEndDate(event.target.value)} /></label>
        <input className="rounded-md border border-slate-300 px-3 py-2 text-sm md:col-span-4" placeholder="说明（可选）" value={description} onChange={(event) => setDescription(event.target.value)} />
        <button disabled={saving} className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60 md:col-span-2">{saving ? "保存中..." : "新增统一假期"}</button>
      </form>

      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead><tr className="border-b border-slate-100 text-left text-slate-400"><th className="px-4 py-3 font-medium">名称</th><th className="px-4 py-3 font-medium">范围</th><th className="px-4 py-3 font-medium">日期</th><th className="px-4 py-3 font-medium">说明</th><th className="px-4 py-3 font-medium" /></tr></thead>
          <tbody>
            {holidays.map((holiday) => (
              <tr key={holiday.id} className="border-b border-slate-50 last:border-0">
                <td className="px-4 py-3 font-medium text-slate-800">{holiday.name}</td>
                <td className="px-4 py-3 text-slate-600">{formatHolidayScope(holiday, departments)}</td>
                <td className="px-4 py-3 whitespace-nowrap text-slate-600">{formatLeaveRange(holiday.start_date, holiday.end_date)}</td>
                <td className="px-4 py-3 text-slate-500">{holiday.description || "-"}</td>
                <td className="px-4 py-3 text-right"><button onClick={() => void remove(holiday)} className="text-xs text-red-500 hover:text-red-700">删除</button></td>
              </tr>
            ))}
            {!loading && holidays.length === 0 && <tr><td colSpan={5} className="px-4 py-5 text-slate-400">暂无统一假期</td></tr>}
            {loading && <tr><td colSpan={5} className="px-4 py-5 text-slate-400">加载中...</td></tr>}
          </tbody>
        </table>
      </div>
    </section>
  );
}
