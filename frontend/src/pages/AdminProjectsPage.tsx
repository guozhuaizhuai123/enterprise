import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  createProject,
  deleteProject,
  listProjects,
  updateProject,
} from "../api/projects";
import type { Project, ProjectInput, ProjectStatus, ProjectType } from "../types";

const TYPE_LABELS: Record<ProjectType, string> = {
  internal: "内部项目",
  client: "客户项目",
  rd: "研发项目",
  other: "其他",
};

const STATUS_LABELS: Record<ProjectStatus, string> = {
  preparing: "筹备中",
  active: "进行中",
  closed: "已结项",
  paused: "已暂停",
  cancelled: "已取消",
};

function errorMessage(error: unknown): string {
  const detail = (error as { response?: { data?: { detail?: string } } }).response?.data?.detail;
  return detail || "操作失败，请稍后重试";
}

export default function AdminProjectsPage() {
  const [items, setItems] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<ProjectStatus | "">("");

  const [editorOpen, setEditorOpen] = useState(false);
  const [selected, setSelected] = useState<Project | null>(null);
  const [form, setForm] = useState<ProjectInput>({
    code: "",
    name: "",
    type: "internal",
    status: "preparing",
    department_id: null,
    manager_id: null,
    start_date: null,
    end_date: null,
    budget: null,
    description: "",
  });

  async function refresh() {
    setLoading(true);
    setError("");
    try {
      const params: Record<string, string> = {};
      if (statusFilter) params.status = statusFilter;
      if (search.trim()) params.q = search.trim();
      setItems(await listProjects(params));
    } catch (loadError) {
      setError(errorMessage(loadError));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter, search]);

  const visible = useMemo(() => {
    const keyword = search.trim().toLowerCase();
    return items.filter(
      (item) =>
        !keyword ||
        item.name.toLowerCase().includes(keyword) ||
        item.code.toLowerCase().includes(keyword),
    );
  }, [items, search]);

  function openCreate() {
    setSelected(null);
    setForm({
      code: "",
      name: "",
      type: "internal",
      status: "preparing",
      department_id: null,
      manager_id: null,
      start_date: null,
      end_date: null,
      budget: null,
      description: "",
    });
    setEditorOpen(true);
  }

  function openEdit(item: Project) {
    setSelected(item);
    setForm({
      code: item.code,
      name: item.name,
      type: item.type,
      status: item.status,
      department_id: item.department_id,
      manager_id: item.manager_id,
      start_date: item.start_date,
      end_date: item.end_date,
      budget: item.budget,
      description: item.description,
    });
    setEditorOpen(true);
  }

  async function save() {
    if (!form.code.trim() || !form.name.trim()) {
      setError("请填写项目编号与名称");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const payload: ProjectInput = {
        ...form,
        budget: form.budget && form.budget.trim() !== "" ? form.budget.trim() : null,
      };
      if (selected) {
        await updateProject(selected.id, payload);
      } else {
        await createProject(payload);
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

  async function remove(item: Project) {
    if (!window.confirm(`确认删除项目「${item.name}」？其下合同将解除关联但保留。`)) return;
    setBusy(true);
    setError("");
    try {
      await deleteProject(item.id);
      await refresh();
    } catch (delError) {
      setError(errorMessage(delError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto w-full max-w-6xl">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">项目管理</h2>
          <p className="mt-1 text-sm text-slate-400">归集与跟踪项目；合同可弱引用归属到项目。</p>
        </div>
        <button
          onClick={openCreate}
          className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500"
        >
          新建项目
        </button>
      </div>

      {error && <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}

      <div className="mt-4 flex flex-wrap gap-3">
        <input
          className="min-w-56 flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm"
          placeholder="搜索项目编号或名称"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select
          className="rounded-md border border-slate-300 px-3 py-2 text-sm"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as ProjectStatus | "")}
        >
          <option value="">全部状态</option>
          {Object.entries(STATUS_LABELS).map(([value, label]) => (
            <option key={value} value={value}>{label}</option>
          ))}
        </select>
      </div>

      {loading ? (
        <p className="mt-6 text-sm text-slate-400">加载中...</p>
      ) : visible.length === 0 ? (
        <p className="mt-6 text-sm text-slate-400">暂无项目</p>
      ) : (
        <div className="mt-4 overflow-x-auto rounded-xl border border-slate-200 bg-white">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs font-medium uppercase tracking-wide text-slate-400">
              <tr>
                <th className="px-4 py-3">编号 / 名称</th>
                <th className="px-4 py-3">类型</th>
                <th className="px-4 py-3">状态</th>
                <th className="px-4 py-3">负责人</th>
                <th className="px-4 py-3">预算</th>
                <th className="px-4 py-3">关联合同</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {visible.map((item) => (
                <tr key={item.id} className="border-t border-slate-100 hover:bg-slate-50">
                  <td className="px-4 py-3">
                    <Link to={`/admin/projects/${item.id}`} className="block hover:text-indigo-700">
                      <div className="font-medium text-slate-800">{item.name}</div>
                      <div className="text-xs text-slate-400">{item.code}</div>
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-slate-600">{TYPE_LABELS[item.type]}</td>
                  <td className="px-4 py-3">
                    <span className="rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-600">{STATUS_LABELS[item.status]}</span>
                  </td>
                  <td className="px-4 py-3 text-slate-500">{item.manager_name || "—"}</td>
                  <td className="px-4 py-3 text-slate-600">{item.budget ? `¥${item.budget}` : "—"}</td>
                  <td className="px-4 py-3 text-slate-500">{item.contract_count} 个</td>
                  <td className="px-4 py-3 text-right">
                    <button onClick={() => openEdit(item)} className="text-indigo-600 hover:text-indigo-800">编辑</button>
                    <button onClick={() => void remove(item)} className="ml-3 text-red-400 hover:text-red-600">删除</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editorOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-black/30 p-6" onClick={() => setEditorOpen(false)}>
          <div className="my-auto w-full max-w-2xl rounded-xl bg-white p-6 shadow-xl" onClick={(event) => event.stopPropagation()}>
            <h2 className="mb-5 text-xl font-semibold text-slate-900">{selected ? "编辑项目" : "新建项目"}</h2>
            <div className="grid grid-cols-2 gap-4">
              <label className="text-sm text-slate-600">
                项目编号
                <input className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} placeholder="如 PRJ-2026-001" />
              </label>
              <label className="text-sm text-slate-600">
                项目名称
                <input className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
              </label>
              <label className="text-sm text-slate-600">
                类型
                <select className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value as ProjectType })}>
                  {Object.entries(TYPE_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </label>
              <label className="text-sm text-slate-600">
                状态
                <select className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value as ProjectStatus })}>
                  {Object.entries(STATUS_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </label>
              <label className="text-sm text-slate-600">
                开始日期
                <input type="date" className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" value={form.start_date ?? ""} onChange={(e) => setForm({ ...form, start_date: e.target.value || null })} />
              </label>
              <label className="text-sm text-slate-600">
                结束日期
                <input type="date" className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" value={form.end_date ?? ""} onChange={(e) => setForm({ ...form, end_date: e.target.value || null })} />
              </label>
              <label className="col-span-2 text-sm text-slate-600">
                预算金额（元）
                <input className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" value={form.budget ?? ""} onChange={(e) => setForm({ ...form, budget: e.target.value || null })} placeholder="选填" />
              </label>
            </div>
            <label className="mt-4 block text-sm text-slate-600">
              说明
              <textarea className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
            </label>
            {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
            <div className="mt-5 flex justify-end gap-2">
              <button onClick={() => setEditorOpen(false)} className="px-4 py-2 text-sm text-slate-500 hover:bg-slate-100">取消</button>
              <button onClick={() => void save()} disabled={busy} className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50">
                {busy ? "保存中..." : "保存"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
