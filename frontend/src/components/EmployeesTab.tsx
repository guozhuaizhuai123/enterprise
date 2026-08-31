import { useEffect, useState } from "react";
import {
  createEmployee,
  listDepartments,
  listEmployees,
  updateEmployeePassword,
} from "../api/admin";
import type { Department, Employee } from "../types";
import { getEmployeeMembershipLabels } from "../adminNavigation";

export default function EmployeesTab({ departmentId }: { departmentId: string }) {
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [loading, setLoading] = useState(true);
  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editPassword, setEditPassword] = useState("");
  const [departments, setDepartments] = useState<Department[]>([]);
  const [selectedDepartmentIds, setSelectedDepartmentIds] = useState<string[]>([departmentId]);
  const [positions, setPositions] = useState<Record<string, string>>({});
  const [activeEmployee, setActiveEmployee] = useState<Employee | null>(null);

  async function refresh() {
    setLoading(true);
    try {
      setEmployees(await listEmployees(departmentId));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    listDepartments().then(setDepartments).catch(() => {});
    setSelectedDepartmentIds([departmentId]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [departmentId]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!newUsername.trim() || !newPassword) return;
    setError("");
    try {
      await createEmployee(
        departmentId,
        newUsername.trim(),
        newPassword,
        selectedDepartmentIds,
        positions,
      );
      setNewUsername("");
      setNewPassword("");
      setPositions({});
      await refresh();
    } catch {
      setError("创建失败，用户名可能已存在");
    }
  }

  async function handleUpdatePassword(id: string) {
    if (!editPassword) return;
    await updateEmployeePassword(id, editPassword);
    setEditingId(null);
    setEditPassword("");
    await refresh();
  }

  return (
    <div>
      <form onSubmit={handleCreate} className="flex gap-2 mb-6">
        <input
          type="password"
          autoComplete="new-password"
          className="rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          placeholder="用户名"
          value={newUsername}
          onChange={(e) => setNewUsername(e.target.value)}
        />
        <input
          className="rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
          placeholder="密码"
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
        />
        <div className="flex-1 space-y-2">
          <p className="text-xs text-slate-500">所属部门（当前部门已默认选中）</p>
          <div className="flex flex-wrap gap-x-4 gap-y-2">
            {departments.map((department) => {
              const selected = selectedDepartmentIds.includes(department.id);
              return (
                <label key={department.id} className="flex items-center gap-1 text-xs text-slate-600">
                  <input
                    type="checkbox"
                    checked={selected}
                    onChange={(e) =>
                      setSelectedDepartmentIds((current) =>
                        e.target.checked
                          ? [...current, department.id]
                          : current.filter((id) => id !== department.id),
                      )
                    }
                  />
                  {department.name}
                </label>
              );
            })}
          </div>
          {selectedDepartmentIds.map((id) => {
            const department = departments.find((item) => item.id === id);
            return (
              <input
                key={id}
                className="rounded border border-slate-300 px-2 py-1 text-xs w-44"
                placeholder={`${department?.name ?? "部门"}职位（可选）`}
                value={positions[id] ?? ""}
                onChange={(e) => setPositions((current) => ({ ...current, [id]: e.target.value }))}
              />
            );
          })}
        </div>
        <button
          type="submit"
          disabled={selectedDepartmentIds.length === 0}
          className="self-start rounded-md bg-indigo-600 text-white px-4 py-2 text-sm font-medium hover:bg-indigo-500 disabled:opacity-60"
        >
          添加员工
        </button>
      </form>
      {error && <p className="text-sm text-red-500 mb-4">{error}</p>}

      {loading ? (
        <p className="text-sm text-slate-400">加载中...</p>
      ) : employees.length === 0 ? (
        <p className="text-sm text-slate-400">该部门暂无员工账号</p>
      ) : (
        <table className="w-full bg-white rounded-lg border border-slate-200 text-sm">
          <thead>
            <tr className="text-left text-slate-400 border-b border-slate-100">
              <th className="px-4 py-2 font-medium">用户名</th>
              <th className="px-4 py-2 font-medium">所属部门 / 职位</th>
              <th className="px-4 py-2 font-medium">账号安全</th>
              <th className="px-4 py-2 font-medium">创建时间</th>
              <th className="px-4 py-2 font-medium"></th>
            </tr>
          </thead>
          <tbody>
            {employees.map((emp) => (
              <tr
                key={emp.id}
                className="border-b border-slate-50 last:border-0 cursor-pointer hover:bg-slate-50"
                onClick={() => setActiveEmployee(emp)}
                title="点击查看员工详情"
              >
                <td className="px-4 py-2 text-slate-800 font-medium">{emp.username}</td>
                <td className="px-4 py-2 text-slate-500">
                  {getEmployeeMembershipLabels(emp).join("、")}
                </td>
                <td className="px-4 py-2">
                  {editingId === emp.id ? (
                    <div className="flex gap-1 items-center">
                      <input
                        type="password"
                        autoComplete="new-password"
                        autoFocus
                        className="rounded border border-slate-300 px-2 py-1 text-xs w-28"
                        value={editPassword}
                        onChange={(e) => setEditPassword(e.target.value)}
                      />
                      <button
                        onClick={(event) => {
                          event.stopPropagation();
                          handleUpdatePassword(emp.id);
                        }}
                        className="text-xs text-indigo-600 hover:text-indigo-800"
                      >
                        保存
                      </button>
                      <button
                        onClick={(event) => {
                          event.stopPropagation();
                          setEditingId(null);
                        }}
                        className="text-xs text-slate-400 hover:text-slate-600"
                      >
                        取消
                      </button>
                    </div>
                  ) : (
                    <span className="text-xs text-emerald-600">密码已加密存储</span>
                  )}
                </td>
                <td className="px-4 py-2 text-slate-400">
                  {new Date(emp.created_at).toLocaleString()}
                </td>
                <td className="px-4 py-2 text-right space-x-3">
                  <button
                    onClick={(event) => {
                      event.stopPropagation();
                      setEditingId(emp.id);
                      setEditPassword("");
                    }}
                    className="text-xs text-slate-400 hover:text-slate-600"
                  >
                    改密码
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {activeEmployee && (
        <div
          className="fixed inset-0 bg-black/30 flex items-center justify-center z-50"
          onClick={() => setActiveEmployee(null)}
        >
          <div
            className="bg-white rounded-lg shadow-lg w-full max-w-md p-6"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-slate-900">员工详情</h3>
              <button
                onClick={() => setActiveEmployee(null)}
                className="text-sm text-slate-400 hover:text-slate-700"
              >
                关闭
              </button>
            </div>
            <dl className="space-y-3 text-sm">
              <div className="flex gap-3">
                <dt className="w-20 text-slate-400">用户名</dt>
                <dd className="text-slate-800">{activeEmployee.username}</dd>
              </div>
              <div>
                <dt className="text-slate-400 mb-1">所属部门 / 职位</dt>
                <dd className="space-y-1 text-slate-800">
                  {(activeEmployee.departments ?? []).map((membership) => (
                    <div key={membership.id}>
                      {membership.name}
                      {membership.position && <span className="text-slate-500"> · {membership.position}</span>}
                    </div>
                  ))}
                  {(!activeEmployee.departments || activeEmployee.departments.length === 0) && (
                    <div className="text-slate-500">部门明细将在后端服务重启后显示</div>
                  )}
                </dd>
              </div>
              <div className="flex gap-3">
                <dt className="w-20 text-slate-400">创建时间</dt>
                <dd className="text-slate-800">{new Date(activeEmployee.created_at).toLocaleString()}</dd>
              </div>
            </dl>
          </div>
        </div>
      )}
    </div>
  );
}
