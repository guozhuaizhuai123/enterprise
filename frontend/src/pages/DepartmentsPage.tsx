import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { createDepartment, deleteDepartment, listDepartments } from "../api/admin";
import { getDepartmentHref } from "../adminNavigation";
import type { Department } from "../types";

export default function DepartmentsPage() {
  const [departments, setDepartments] = useState<(Department & { employee_count: number; document_count: number })[]>(
    [],
  );
  const [loading, setLoading] = useState(true);
  const [newName, setNewName] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");

  async function refresh() {
    setLoading(true);
    try {
      const data = await listDepartments();
      setDepartments(data as never);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!newName.trim()) return;
    setCreating(true);
    setError("");
    try {
      await createDepartment(newName.trim());
      setNewName("");
      await refresh();
    } catch {
      setError("创建失败，部门名可能已存在");
    } finally {
      setCreating(false);
    }
  }

  async function handleDelete(id: string) {
    if (!confirm("确定删除该部门？部门下的员工和文档也会被删除。")) return;
    await deleteDepartment(id);
    await refresh();
  }

  return (
    <div className="mx-auto w-full max-w-4xl">
      <h2 className="text-lg font-semibold text-slate-900 mb-4">部门列表</h2>

      <form onSubmit={handleCreate} className="flex gap-2 mb-6">
        <input
          className="rounded-md border border-slate-300 px-3 py-2 text-sm flex-1 max-w-xs focus:outline-none focus:ring-2 focus:ring-indigo-500"
          placeholder="新部门名称"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
        />
        <button
          type="submit"
          disabled={creating}
          className="rounded-md bg-indigo-600 text-white px-4 py-2 text-sm font-medium hover:bg-indigo-500 disabled:opacity-60"
        >
          创建部门
        </button>
      </form>
      {error && <p className="text-sm text-red-500 mb-4">{error}</p>}

      {loading ? (
        <p className="text-sm text-slate-400">加载中...</p>
      ) : departments.length === 0 ? (
        <p className="text-sm text-slate-400">暂无部门，先创建一个</p>
      ) : (
        <div className="bg-white rounded-lg border border-slate-200 divide-y divide-slate-100">
          {departments.map((d) => (
            <div key={d.id} className="flex items-stretch justify-between">
              <Link
                to={getDepartmentHref(d.id)}
                className="flex flex-1 items-center px-4 py-3 hover:bg-slate-50"
              >
                <span className="font-medium text-slate-800">{d.name}</span>
                <span className="ml-3 text-xs text-slate-400">
                  {d.employee_count} 名员工 · {d.document_count} 篇文档
                </span>
              </Link>
              <button
                onClick={() => handleDelete(d.id)}
                className="text-xs text-red-400 hover:text-red-600 px-4 py-3"
              >
                删除
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
