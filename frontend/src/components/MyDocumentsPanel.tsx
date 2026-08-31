import { useEffect, useState } from "react";
import {
  createMyDocument,
  deleteMyDocument,
  getMyDocument,
  listMyDocuments,
  updateMyDocument,
} from "../api/kb";
import { canEditOwnedDocument, formatOwnerLabel } from "../adminNavigation";
import { useAuthStore } from "../store/auth";
import type { DocumentDetail, DocumentItem } from "../types";

interface FormState {
  id: string | null;
  department_id: string;
  title: string;
  category: string;
  sensitive: boolean;
  content: string;
}

const blankForm: FormState = {
  id: null,
  department_id: "",
  title: "",
  category: "",
  sensitive: false,
  content: "",
};

export default function MyDocumentsPanel() {
  const [docs, setDocs] = useState<DocumentItem[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState<DocumentDetail | null>(null);
  const [form, setForm] = useState<FormState | null>(null);
  const [loadingId, setLoadingId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const { userId, departments } = useAuthStore();

  async function refresh() {
    setDocs(await listMyDocuments());
  }

  useEffect(() => {
    refresh().catch(() => {});
  }, []);

  async function openDocument(id: string) {
    setLoadingId(id);
    try {
      setActive(await getMyDocument(id));
    } finally {
      setLoadingId(null);
    }
  }

  function openCreate() {
    setError("");
    setOpen(true);
    setForm({ ...blankForm, department_id: departments[0]?.id ?? "" });
  }

  async function openEdit(id: string) {
    setLoadingId(id);
    try {
      const detail = await getMyDocument(id);
      setError("");
      setForm({
        id: detail.id,
        department_id: detail.department_id,
        title: detail.title,
        category: detail.category,
        sensitive: detail.sensitive,
        content: detail.content,
      });
    } finally {
      setLoadingId(null);
    }
  }

  async function handleSave() {
    if (!form || !form.department_id || !form.title.trim() || !form.content.trim()) return;
    setSaving(true);
    setError("");
    try {
      if (form.id) {
        await updateMyDocument(form.id, {
          title: form.title.trim(),
          category: form.category.trim(),
          sensitive: form.sensitive,
          content: form.content,
        });
      } else {
        await createMyDocument({
          department_id: form.department_id,
          title: form.title.trim(),
          category: form.category.trim(),
          sensitive: form.sensitive,
          content: form.content,
        });
      }
      setForm(null);
      await refresh();
    } catch {
      setError("保存失败，请确认目标部门属于你的授权范围");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: string) {
    if (!confirm("确定删除该文档？")) return;
    try {
      await deleteMyDocument(id);
      await refresh();
      setActive(null);
    } catch {
      setError("删除失败");
    }
  }

  function departmentName(id: string): string {
    return departments.find((department) => department.id === id)?.name ?? "未知部门";
  }

  return (
    <div className="border-t border-slate-200 pt-3">
      <div className="flex items-center justify-between">
        <button
          onClick={() => setOpen((value) => !value)}
          className="text-sm font-medium text-slate-600 flex items-center gap-2"
        >
          <span>知识文档 ({docs.length})</span>
          <span className="text-slate-400">{open ? "▾" : "▸"}</span>
        </button>
        <button onClick={openCreate} className="text-xs text-indigo-600 hover:text-indigo-800">
          上传文档
        </button>
      </div>
      {error && <p className="text-xs text-red-500 mt-2">{error}</p>}
      {open && (
        <ul className="mt-2 space-y-1 max-h-56 overflow-y-auto text-sm">
          {docs.map((doc) => {
            const canEdit = canEditOwnedDocument(doc.owner_id, userId);
            return (
              <li key={doc.id} className="flex items-center gap-1">
                <button
                  onClick={() => openDocument(doc.id)}
                  disabled={loadingId === doc.id}
                  className="min-w-0 flex-1 text-left text-slate-500 hover:text-indigo-600 truncate disabled:opacity-60"
                >
                  <span>{doc.title}</span>
                  <span className="ml-1 text-xs text-slate-400">[{departmentName(doc.department_id)}]</span>
                  <span className="ml-1 text-xs text-slate-400">
                    · {formatOwnerLabel(doc.owner_name, doc.owner_active)}
                  </span>
                  {doc.project_name && <span className="ml-1 text-xs text-indigo-500">· 项目：{doc.project_name}</span>}
                  {doc.contract_name && <span className="ml-1 text-xs text-emerald-600">· 合同：{doc.contract_name}</span>}
                </button>
                {canEdit && (
                  <>
                    <button onClick={() => openEdit(doc.id)} className="shrink-0 text-xs text-slate-400 hover:text-indigo-600">编辑</button>
                    <button onClick={() => handleDelete(doc.id)} className="shrink-0 text-xs text-slate-400 hover:text-red-600">删除</button>
                  </>
                )}
              </li>
            );
          })}
          {docs.length === 0 && <li className="text-slate-400 text-xs">暂无文档</li>}
        </ul>
      )}

      {active && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={() => setActive(null)}>
          <div className="bg-white rounded-lg shadow-lg w-full max-w-2xl p-6 max-h-[80vh] overflow-y-auto" onClick={(event) => event.stopPropagation()}>
            <div className="flex items-center justify-between mb-3">
              <div>
                <h3 className="font-semibold text-slate-900">{active.title}</h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  {active.category && <span className="mr-2">[{active.category}]</span>}
                  {departmentName(active.department_id)} · {formatOwnerLabel(active.owner_name, active.owner_active)}
                  {active.project_name && <span className="ml-2">· 项目：{active.project_name}</span>}
                  {active.contract_name && <span className="ml-2">· 合同：{active.contract_name}</span>}
                </p>
              </div>
              <button onClick={() => setActive(null)} className="text-sm text-slate-400 hover:text-slate-700">关闭</button>
            </div>
            <p className="text-sm text-slate-700 whitespace-pre-wrap leading-relaxed">{active.content}</p>
          </div>
        </div>
      )}

      {form && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={() => setForm(null)}>
          <div className="bg-white rounded-lg shadow-lg w-full max-w-2xl p-6 max-h-[85vh] overflow-y-auto" onClick={(event) => event.stopPropagation()}>
            <h3 className="font-semibold text-slate-900 mb-4">{form.id ? "编辑我的文档" : "上传文档"}</h3>
            <div className="space-y-3">
              {!form.id && (
                <label className="block text-sm text-slate-600">
                  <span className="block mb-1">上传到部门</span>
                  <select className="w-full rounded-md border border-slate-300 px-3 py-2" value={form.department_id} onChange={(event) => setForm({ ...form, department_id: event.target.value })}>
                    {departments.map((department) => <option key={department.id} value={department.id}>{department.name}</option>)}
                  </select>
                </label>
              )}
              <div className="flex gap-3">
                <input className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm" placeholder="标题" value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} />
                <input className="w-40 rounded-md border border-slate-300 px-3 py-2 text-sm" placeholder="分类（可选）" value={form.category} onChange={(event) => setForm({ ...form, category: event.target.value })} />
              </div>
              <label className="flex items-center gap-2 text-sm text-slate-600">
                <input type="checkbox" checked={form.sensitive} onChange={(event) => setForm({ ...form, sensitive: event.target.checked })} />
                标记为敏感文档
              </label>
              <textarea className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm h-64 font-mono" placeholder="文档内容" value={form.content} onChange={(event) => setForm({ ...form, content: event.target.value })} />
            </div>
            {error && <p className="text-sm text-red-500 mt-2">{error}</p>}
            <div className="flex justify-end gap-2 mt-4">
              <button onClick={() => setForm(null)} className="px-4 py-2 text-sm text-slate-500 hover:text-slate-700">取消</button>
              <button onClick={handleSave} disabled={saving || departments.length === 0} className="rounded-md bg-indigo-600 text-white px-4 py-2 text-sm font-medium hover:bg-indigo-500 disabled:opacity-60">
                {saving ? "保存中..." : "保存"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
