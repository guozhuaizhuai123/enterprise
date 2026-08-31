import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import {
  createOrgEmployee,
  createOrgUnit,
  listOrgEmployees,
  listOrgUnits,
  offboardEmployee,
  resetEmployeePassword,
  updateOrgEmployee,
  updateOrgUnit,
} from "../api/organization";
import EmployeeForm from "../components/EmployeeForm";
import OrgUnitEditor from "../components/OrgUnitEditor";
import type { OrgUnitUpdateInput } from "../components/OrgUnitEditor";
import CompanyStructureOverview from "../components/CompanyStructureOverview";
import {
  formatEmployeeDisplayName,
  formatEmploymentStatus,
  formatOrgMemberships,
} from "../organizationFormat";
import type {
  EmploymentStatus,
  OrgEmployee,
  OrgEmployeeInput,
  OrgEmployeeUpdate,
  OrgUnit,
} from "../types";
import { useAuthStore } from "../store/auth";

function errorMessage(error: unknown): string {
  const detail = (error as { response?: { data?: { detail?: string } } }).response?.data?.detail;
  return detail || "操作失败，请稍后重试";
}

export default function OrganizationPage() {
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const { role, roles } = useAuthStore();
  const insideAdmin = location.pathname.startsWith("/admin/");
  const canWrite = role === "admin" || roles.includes("hr");
  const [units, setUnits] = useState<OrgUnit[]>([]);
  const [employees, setEmployees] = useState<OrgEmployee[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [departmentFilter, setDepartmentFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState<EmploymentStatus | "">("");
  const [editorOpen, setEditorOpen] = useState(false);
  const [selected, setSelected] = useState<OrgEmployee | null>(null);
  const [newUnitName, setNewUnitName] = useState("");
  const [newUnitCode, setNewUnitCode] = useState("");
  const [newUnitManagerId, setNewUnitManagerId] = useState("");
  const [editingUnit, setEditingUnit] = useState<OrgUnit | null>(null);
  const [resetTarget, setResetTarget] = useState<OrgEmployee | null>(null);
  const [newPassword, setNewPassword] = useState("");

  async function refresh() {
    setLoading(true);
    setError("");
    try {
      const [nextUnits, nextEmployees] = await Promise.all([
        listOrgUnits(),
        listOrgEmployees(),
      ]);
      setUnits(nextUnits);
      setEmployees(nextEmployees);
      if (selected) {
        setSelected(nextEmployees.find((item) => item.id === selected.id) ?? null);
      }
    } catch (loadError) {
      setError(errorMessage(loadError));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const requestedStatus = searchParams.get("status") as EmploymentStatus | null;
    if (requestedStatus && ["probation", "active", "suspended", "terminated"].includes(requestedStatus)) {
      setStatusFilter(requestedStatus);
    }
    void refresh();
    // The initial fetch is intentionally performed once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const visibleEmployees = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    return employees.filter((employee) => {
      const matchesSearch = !keyword || [employee.username, employee.full_name, employee.phone, employee.email, employee.position]
        .some((value) => value.toLowerCase().includes(keyword));
      const matchesDepartment = !departmentFilter || employee.departments.some((item) => item.department_id === departmentFilter);
      const matchesStatus = !statusFilter || employee.status === statusFilter;
      return matchesSearch && matchesDepartment && matchesStatus;
    });
  }, [departmentFilter, employees, search, statusFilter]);

  async function saveEmployee(data: OrgEmployeeInput | OrgEmployeeUpdate) {
    setBusy(true);
    setError("");
    try {
      if (selected) {
        await updateOrgEmployee(selected.id, data as OrgEmployeeUpdate);
      } else {
        await createOrgEmployee(data as OrgEmployeeInput);
      }
      setEditorOpen(false);
      setSelected(null);
      await refresh();
    } catch (saveError) {
      setError(errorMessage(saveError));
    } finally {
      setBusy(false);
    }
  }

  async function addUnit(event: React.FormEvent) {
    event.preventDefault();
    if (!newUnitName.trim() || !newUnitCode.trim()) return;
    setBusy(true);
    setError("");
    try {
      await createOrgUnit({
        name: newUnitName.trim(),
        code: newUnitCode.trim().toUpperCase(),
        manager_id: newUnitManagerId || null,
      });
      setNewUnitName("");
      setNewUnitCode("");
      setNewUnitManagerId("");
      await refresh();
    } catch (createError) {
      setError(errorMessage(createError));
    } finally {
      setBusy(false);
    }
  }

  async function updateUnit(data: OrgUnitUpdateInput) {
    if (!editingUnit) return;
    setBusy(true);
    setError("");
    try {
      await updateOrgUnit(editingUnit.id, data);
      setEditingUnit(null);
      await refresh();
    } catch (saveError) {
      setError(errorMessage(saveError));
    } finally {
      setBusy(false);
    }
  }

  async function confirmReset() {
    if (!resetTarget || newPassword.length < 8) return;
    setBusy(true);
    setError("");
    try {
      await resetEmployeePassword(resetTarget.id, newPassword);
      setResetTarget(null);
      setNewPassword("");
    } catch (resetError) {
      setError(errorMessage(resetError));
    } finally {
      setBusy(false);
    }
  }

  async function offboard(employee: OrgEmployee) {
    if (!window.confirm(`确认将 ${employee.full_name || employee.username} 办理离职？历史业务数据会保留。`)) return;
    setBusy(true);
    setError("");
    try {
      await offboardEmployee(employee.id, {
        effective_date: new Date().toISOString().slice(0, 10),
        note: "管理后台办理离职",
      });
      setSelected(null);
      await refresh();
    } catch (offboardError) {
      setError(errorMessage(offboardError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      {!insideAdmin && <div className="flex items-center gap-4 border-b border-slate-200 pb-4"><Link to="/chat" className="text-sm text-indigo-600">← 返回知识助手</Link></div>}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">组织与员工</h1>
          <p className="mt-1 text-sm text-slate-500">统一管理员工档案、汇报关系、部门归属和业务角色。</p>
        </div>
        {canWrite && <button
          onClick={() => { setSelected(null); setEditorOpen(true); }}
          disabled={units.length === 0}
          className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
        >
          新增员工
        </button>}
      </div>

      {error && <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}

      {!loading && <CompanyStructureOverview units={units} employees={employees} />}

      <section className="grid gap-4 lg:grid-cols-[2fr_1fr]">
        <div className="rounded-xl border border-slate-200 bg-white p-5">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="font-semibold text-slate-900">部门架构</h2>
            <span className="text-xs text-slate-400">{units.filter((unit) => unit.active).length} 个启用部门</span>
          </div>
          {units.length === 0 ? (
            <p className="py-8 text-center text-sm text-slate-400">尚未建立部门，请先创建第一个组织单元。</p>
          ) : (
            <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
              {units.map((unit) => {
                const parent = units.find((item) => item.id === unit.parent_id);
                const manager = employees.find((item) => item.id === unit.manager_id);
                const managerLabel = unit.manager_name || (manager ? manager.full_name || manager.username : "");
                const count = employees.filter((employee) => employee.departments.some((membership) => membership.department_id === unit.id)).length;
                return (
                  <div key={unit.id} className={`rounded-lg border p-3 transition ${departmentFilter === unit.id ? "border-indigo-400 bg-indigo-50" : "border-slate-200 hover:border-slate-300"}`}>
                    <div className="flex items-center justify-between">
                      <button onClick={() => setDepartmentFilter(unit.id)} className="text-left font-medium text-slate-800">
                        {unit.name}
                        {!unit.active && <span className="ml-2 rounded bg-slate-200 px-1.5 py-0.5 text-[10px] text-slate-500">已停用</span>}
                      </button>
                      <span className="text-xs text-slate-400">{unit.code}</span>
                    </div>
                    <p className="mt-2 text-xs text-slate-400">{parent ? `上级：${parent.name}` : "一级部门"} · {count} 人</p>
                    <p className="mt-1 text-xs text-slate-500">部门负责人：<span className={managerLabel ? "text-slate-700" : "text-amber-700"}>{managerLabel || "未设置"}</span></p>
                    {canWrite && (
                      <button onClick={() => setEditingUnit(unit)} className="mt-2 text-xs font-medium text-indigo-600 hover:text-indigo-800">
                        设置部门
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {canWrite ? <form onSubmit={addUnit} className="rounded-xl border border-slate-200 bg-white p-5">
          <h2 className="font-semibold text-slate-900">快速创建部门</h2>
          <p className="mt-1 text-xs text-slate-400">创建时即可指定负责人，之后也能在「设置部门」里调整。</p>
          <input className="mt-4 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" placeholder="部门名称" value={newUnitName} onChange={(e) => setNewUnitName(e.target.value)} />
          <input className="mt-3 w-full rounded-md border border-slate-300 px-3 py-2 text-sm uppercase" placeholder="部门编码，如 SALES" value={newUnitCode} onChange={(e) => setNewUnitCode(e.target.value)} />
          <select className="mt-3 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" value={newUnitManagerId} onChange={(e) => setNewUnitManagerId(e.target.value)}>
            <option value="">部门负责人（可选）</option>
            {employees.filter((item) => item.status !== "terminated").map((item) => (
              <option key={item.id} value={item.id}>{item.full_name || item.username}</option>
            ))}
          </select>
          <button disabled={busy} className="mt-3 w-full rounded-md border border-indigo-200 px-3 py-2 text-sm font-medium text-indigo-700 hover:bg-indigo-50 disabled:opacity-50">创建部门</button>
        </form> : <div className="rounded-xl border border-slate-200 bg-white p-5"><h2 className="font-semibold text-slate-900">负责人视图</h2><p className="mt-2 text-sm text-slate-500">你可以查看直属员工与组织关系；员工档案变更由 HR 或管理员处理。</p></div>}
      </section>

      <section className="overflow-hidden rounded-xl border border-slate-200 bg-white">
        <div className="flex flex-wrap gap-3 border-b border-slate-100 p-4">
          <input className="min-w-56 flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm" placeholder="搜索姓名、账号、岗位、手机或邮箱" value={search} onChange={(e) => setSearch(e.target.value)} />
          <select className="rounded-md border border-slate-300 px-3 py-2 text-sm" value={departmentFilter} onChange={(e) => setDepartmentFilter(e.target.value)}>
            <option value="">全部部门</option>
            {units.map((unit) => <option key={unit.id} value={unit.id}>{unit.name}</option>)}
          </select>
          <select className="rounded-md border border-slate-300 px-3 py-2 text-sm" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as EmploymentStatus | "")}>
            <option value="">全部状态</option>
            <option value="probation">试用期</option>
            <option value="active">在职</option>
            <option value="suspended">停职</option>
            <option value="terminated">已离职</option>
          </select>
        </div>
        {loading ? (
          <p className="p-10 text-center text-sm text-slate-400">正在加载组织数据...</p>
        ) : visibleEmployees.length === 0 ? (
          <p className="p-10 text-center text-sm text-slate-400">没有符合条件的员工</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs font-medium uppercase tracking-wide text-slate-400">
                <tr><th className="px-4 py-3">员工</th><th className="px-4 py-3">部门 / 岗位</th><th className="px-4 py-3">直属上级</th><th className="px-4 py-3">角色</th><th className="px-4 py-3">状态</th><th className="px-4 py-3"></th></tr>
              </thead>
              <tbody>
                {visibleEmployees.map((employee) => (
                  <tr key={employee.id} className="border-t border-slate-100 hover:bg-slate-50">
                    <td className="px-4 py-3"><div className="font-medium text-slate-800">{formatEmployeeDisplayName(employee)}</div><div className="text-xs text-slate-400">{employee.username}</div></td>
                    <td className="px-4 py-3 text-slate-600">{formatOrgMemberships(employee.departments).join("、") || "未分配"}</td>
                    <td className="px-4 py-3 text-slate-500">{employee.manager_name || "—"}</td>
                    <td className="px-4 py-3 text-slate-500">{employee.roles.join(" / ")}</td>
                    <td className="px-4 py-3"><span className={`rounded-full px-2 py-1 text-xs ${employee.status === "terminated" ? "bg-slate-100 text-slate-500" : employee.status === "suspended" ? "bg-amber-100 text-amber-700" : "bg-emerald-100 text-emerald-700"}`}>{formatEmploymentStatus(employee.status)}</span></td>
                    <td className="px-4 py-3 text-right"><button onClick={() => setSelected(employee)} className="text-indigo-600 hover:text-indigo-800">查看档案</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {selected && !editorOpen && (
        <div className="fixed inset-0 z-40 flex justify-end bg-black/30" onClick={() => setSelected(null)}>
          <aside className="h-full w-full max-w-lg overflow-y-auto bg-white p-6 shadow-xl" onClick={(event) => event.stopPropagation()}>
            <div className="flex items-start justify-between">
              <div><h2 className="text-xl font-semibold text-slate-900">{formatEmployeeDisplayName(selected)}</h2><p className="text-sm text-slate-400">账号：{selected.username}</p></div>
              <button onClick={() => setSelected(null)} className="text-slate-400 hover:text-slate-700">关闭</button>
            </div>
            <dl className="mt-6 grid grid-cols-2 gap-4 text-sm">
              <div><dt className="text-slate-400">部门 / 岗位</dt><dd className="mt-1 text-slate-700">{formatOrgMemberships(selected.departments).join("、") || "—"}</dd></div>
              <div><dt className="text-slate-400">职级</dt><dd className="mt-1 text-slate-700">{selected.level || "—"}</dd></div>
              <div><dt className="text-slate-400">直属上级</dt><dd className="mt-1 text-slate-700">{selected.manager_name || "—"}</dd></div>
              <div><dt className="text-slate-400">薪资</dt><dd className="mt-1 text-slate-700">{selected.salary || "—"}</dd></div>
              <div><dt className="text-slate-400">联系方式</dt><dd className="mt-1 text-slate-700">{selected.phone || selected.email || "—"}</dd></div>
              <div><dt className="text-slate-400">入职日期</dt><dd className="mt-1 text-slate-700">{selected.hire_date || "—"}</dd></div>
            </dl>
            {selected.notes && <p className="mt-5 rounded-lg bg-slate-50 p-3 text-sm text-slate-600">{selected.notes}</p>}
            {canWrite && <div className="mt-8 flex flex-wrap gap-2 border-t border-slate-100 pt-5">
              <button onClick={() => setEditorOpen(true)} className="rounded-md bg-indigo-600 px-3 py-2 text-sm text-white hover:bg-indigo-500">编辑档案</button>
              <button onClick={() => { setResetTarget(selected); setNewPassword(""); }} className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-600 hover:bg-slate-50">重置密码</button>
              {selected.status !== "terminated" && <button onClick={() => void offboard(selected)} disabled={busy} className="rounded-md border border-red-200 px-3 py-2 text-sm text-red-600 hover:bg-red-50">办理离职</button>}
            </div>}
          </aside>
        </div>
      )}

      {editorOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-black/30 p-6">
          <div className="my-auto w-full max-w-3xl rounded-xl bg-white p-6 shadow-xl">
            <h2 className="mb-5 text-xl font-semibold text-slate-900">{selected ? "编辑员工档案" : "新增员工"}</h2>
            <EmployeeForm employee={selected} units={units} employees={employees} busy={busy} onSave={saveEmployee} onCancel={() => { setEditorOpen(false); setSelected(null); }} />
          </div>
        </div>
      )}

      {editingUnit && (
        <div className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-black/30 p-6" onClick={() => setEditingUnit(null)}>
          <div className="my-auto w-full max-w-lg rounded-xl bg-white p-6 shadow-xl" onClick={(event) => event.stopPropagation()}>
            <div className="mb-5 flex items-start justify-between">
              <h2 className="text-xl font-semibold text-slate-900">设置部门</h2>
              <button onClick={() => setEditingUnit(null)} className="text-slate-400 hover:text-slate-700">关闭</button>
            </div>
            <p className="mb-4 text-sm text-slate-500">调整部门名称、层级、负责人与启用状态，变更立即生效。</p>
            <OrgUnitEditor unit={editingUnit} units={units} employees={employees} busy={busy} onSave={updateUnit} onCancel={() => setEditingUnit(null)} />
          </div>
        </div>
      )}

      {resetTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-6" onClick={() => setResetTarget(null)}>
          <div className="w-full max-w-sm rounded-xl bg-white p-6 shadow-xl" onClick={(event) => event.stopPropagation()}>
            <h2 className="font-semibold text-slate-900">重置 {resetTarget.full_name || resetTarget.username} 的密码</h2>
            <p className="mt-1 text-xs text-slate-400">系统不会显示旧密码；新密码至少 8 位。</p>
            <input type="password" autoComplete="new-password" className="mt-4 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" placeholder="输入新密码" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} />
            <div className="mt-4 flex justify-end gap-2"><button onClick={() => setResetTarget(null)} className="px-3 py-2 text-sm text-slate-500">取消</button><button onClick={() => void confirmReset()} disabled={busy || newPassword.length < 8} className="rounded-md bg-indigo-600 px-3 py-2 text-sm text-white disabled:opacity-50">确认重置</button></div>
          </div>
        </div>
      )}
    </div>
  );
}
