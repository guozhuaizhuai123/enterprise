import { useEffect, useState } from "react";
import {
  createDocument,
  deleteDocument,
  getDocument,
  listOwnerOptions,
  listDepartmentDocuments,
  updateDocument,
} from "../api/admin";
import type { DocumentItem } from "../types";
import { formatOwnerLabel } from "../adminNavigation";
import { useAuthStore } from "../store/auth";
import { listContracts, listProjects } from "../api/projects";
import type { Contract, Project } from "../types";

interface FormState {
  id: string | null;
  title: string;
  category: string;
  sensitive: boolean;
  content: string;
  owner_id: string;
  project_id: string;
  contract_id: string;
}

const emptyForm: FormState = { id: null, title: "", category: "", sensitive: false, content: "", owner_id: "", project_id: "", contract_id: "" };

export default function DocumentsTab({ departmentId }: { departmentId: string }) {
  const [docs, setDocs] = useState<DocumentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState<FormState | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [ownerOptions, setOwnerOptions] = useState<{ id: string; username: string; role: string }[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [contracts, setContracts] = useState<Contract[]>([]);
  const adminId = useAuthStore((state) => state.userId);

  async function refresh() {
    setLoading(true);
    try {
      setDocs(await listDepartmentDocuments(departmentId));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    listOwnerOptions().then(setOwnerOptions).catch(() => {});
    listProjects().then(setProjects).catch(() => {});
    listContracts().then(setContracts).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [departmentId]);

  async function openEdit(doc: DocumentItem) {
    const detail = await getDocument(doc.id);
    setForm({
      id: detail.id,
      title: detail.title,
      category: detail.category,
      sensitive: detail.sensitive,
      content: detail.content,
      owner_id: detail.owner_id ?? "",
      project_id: detail.project_id ?? "",
      contract_id: detail.contract_id ?? "",
    });
  }

  async function handleSave() {
    if (!form || !form.title.trim() || !form.content.trim()) return;
    setSaving(true);
    setError("");
    try {
      if (form.id) {
        await updateDocument(form.id, {
          title: form.title,
          category: form.category,
          sensitive: form.sensitive,
          content: form.content,
          ...(form.owner_id ? { owner_id: form.owner_id } : {}),
          project_id: form.project_id || null,
          contract_id: form.contract_id || null,
        });
      } else {
        await createDocument(departmentId, {
          title: form.title,
          category: form.category,
          sensitive: form.sensitive,
          content: form.content,
          ...(form.owner_id ? { owner_id: form.owner_id } : {}),
          project_id: form.project_id || null,
          contract_id: form.contract_id || null,
        });
      }
      setForm(null);
      await refresh();
    } catch {
      setError("保存失败");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: string) {
    if (!confirm("确定删除该文档？")) return;
    await deleteDocument(id);
    await refresh();
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-4">
        <p className="text-sm text-slate-400">
          文档上传后会自动向量化并缓存到检索索引，无需每次提问重新构建
        </p>
        <button
          onClick={() => setForm({ ...emptyForm, owner_id: adminId ?? "" })}
          className="rounded-md bg-indigo-600 text-white px-4 py-2 text-sm font-medium hover:bg-indigo-500"
        >
          新建文档
        </button>
      </div>

      {loading ? (
        <p className="text-sm text-slate-400">加载中...</p>
      ) : docs.length === 0 ? (
        <p className="text-sm text-slate-400">该部门暂无文档</p>
      ) : (
        <div className="bg-white rounded-lg border border-slate-200 divide-y divide-slate-100">
          {docs.map((doc) => (
            <div key={doc.id} className="flex items-center justify-between px-4 py-3">
              <div className="flex-1 cursor-pointer" onClick={() => openEdit(doc)}>
                <span className="font-medium text-slate-800">{doc.title}</span>
                {doc.category && (
                  <span className="ml-2 text-xs bg-slate-100 text-slate-500 px-2 py-0.5 rounded">
                    {doc.category}
                  </span>
                )}
                {doc.sensitive && (
                  <span className="ml-2 text-xs bg-amber-100 text-amber-600 px-2 py-0.5 rounded">敏感</span>
                )}
                <span className="ml-3 text-xs text-slate-400">
                  更新于 {new Date(doc.updated_at).toLocaleString()}
                </span>
                <span className="ml-3 text-xs text-slate-500">
                  所属人：{formatOwnerLabel(doc.owner_name, doc.owner_active)}
                </span>
              </div>
              <button
                onClick={() => handleDelete(doc.id)}
                className="text-xs text-red-400 hover:text-red-600 ml-4"
              >
                删除
              </button>
            </div>
          ))}
        </div>
      )}

      {form && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50" onClick={() => setForm(null)}>
          <div
            className="bg-white rounded-lg shadow-lg w-full max-w-2xl p-6 max-h-[85vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="font-semibold text-slate-900 mb-4">{form.id ? "编辑文档" : "新建文档"}</h3>
            <div className="space-y-3">
              <div className="flex gap-3">
                <input
                  className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm"
                  placeholder="标题"
                  value={form.title}
                  onChange={(e) => setForm({ ...form, title: e.target.value })}
                />
                <input
                  className="w-40 rounded-md border border-slate-300 px-3 py-2 text-sm"
                  placeholder="分类（可选）"
                  value={form.category}
                  onChange={(e) => setForm({ ...form, category: e.target.value })}
                />
              </div>
              <label className="flex items-center gap-2 text-sm text-slate-600">
                <input
                  type="checkbox"
                  checked={form.sensitive}
                  onChange={(e) => setForm({ ...form, sensitive: e.target.checked })}
                />
                标记为敏感文档
              </label>
              <div className="flex gap-3">
                <label className="flex-1 text-sm text-slate-600">项目<select className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" value={form.project_id} onChange={(e) => setForm({ ...form, project_id: e.target.value, contract_id: "" })}><option value="">未归属项目</option>{projects.map((project) => <option key={project.id} value={project.id}>{project.name}（{project.code}）</option>)}</select></label>
                <label className="flex-1 text-sm text-slate-600">合同<select className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" value={form.contract_id} onChange={(e) => setForm({ ...form, contract_id: e.target.value })}><option value="">未关联合同</option>{contracts.filter((contract) => !form.project_id || contract.project_id === form.project_id).map((contract) => <option key={contract.id} value={contract.id}>{contract.name}（{contract.code}）</option>)}</select></label>
              </div>
              <label className="flex items-center gap-2 text-sm text-slate-600">
                <span className="shrink-0">所属人</span>
                <select
                  className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm"
                  value={form.owner_id}
                  onChange={(e) => setForm({ ...form, owner_id: e.target.value })}
                >
                  {!form.owner_id && <option value="">{form.id ? "原所属人已离职" : "选择所属人"}</option>}
                  {ownerOptions.map((owner) => (
                    <option key={owner.id} value={owner.id}>{owner.username}</option>
                  ))}
                </select>
              </label>
              <textarea
                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm h-64 font-mono"
                placeholder="文档内容"
                value={form.content}
                onChange={(e) => setForm({ ...form, content: e.target.value })}
              />
            </div>
            {error && <p className="text-sm text-red-500 mt-2">{error}</p>}
            <div className="flex justify-end gap-2 mt-4">
              <button
                onClick={() => setForm(null)}
                className="px-4 py-2 text-sm text-slate-500 hover:text-slate-700"
              >
                取消
              </button>
              <button
                onClick={handleSave}
                disabled={saving}
                className="rounded-md bg-indigo-600 text-white px-4 py-2 text-sm font-medium hover:bg-indigo-500 disabled:opacity-60"
              >
                {saving ? "保存中..." : "保存"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
