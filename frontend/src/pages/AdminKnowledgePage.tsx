import { useEffect, useMemo, useState } from "react";
import {
  createDocument,
  deleteDocument,
  getDocument,
  listAdminDocuments,
  listDepartments,
  listOwnerOptions,
  updateDocument,
} from "../api/admin";
import { listContracts, listProjects } from "../api/projects";
import { useAuthStore } from "../store/auth";
import type { Contract, Department, DocumentDetail, DocumentItem, Project, UserOption } from "../types";

interface FormState {
  id: string | null;
  department_id: string;
  title: string;
  category: string;
  sensitive: boolean;
  content: string;
  owner_id: string;
  project_id: string;
  contract_id: string;
}

const blankForm: FormState = { id: null, department_id: "", title: "", category: "", sensitive: false, content: "", owner_id: "", project_id: "", contract_id: "" };

function errorMessage(error: unknown): string {
  const detail = (error as { response?: { data?: { detail?: string } } }).response?.data?.detail;
  return detail || "操作失败，请稍后重试";
}

export default function AdminKnowledgePage() {
  const adminId = useAuthStore((state) => state.userId);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [contracts, setContracts] = useState<Contract[]>([]);
  const [owners, setOwners] = useState<UserOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [departmentFilter, setDepartmentFilter] = useState("");
  const [projectFilter, setProjectFilter] = useState("");
  const [contractFilter, setContractFilter] = useState("");
  const [sensitiveFilter, setSensitiveFilter] = useState("");
  const [form, setForm] = useState<FormState | null>(null);
  const [saving, setSaving] = useState(false);

  async function refresh() {
    setLoading(true);
    setError("");
    try {
      const params: Record<string, string> = {};
      if (search.trim()) params.q = search.trim();
      if (departmentFilter) params.department_id = departmentFilter;
      if (projectFilter) params.project_id = projectFilter;
      if (contractFilter) params.contract_id = contractFilter;
      if (sensitiveFilter) params.sensitive = sensitiveFilter;
      setDocuments(await listAdminDocuments(params));
    } catch (loadError) {
      setError(errorMessage(loadError));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void Promise.all([listDepartments(), listProjects(), listContracts(), listOwnerOptions()]).then(([dept, projectList, contractList, ownerList]) => {
      setDepartments(dept); setProjects(projectList); setContracts(contractList); setOwners(ownerList);
    }).catch(() => setError("知识文档基础数据加载失败"));
  }, []);

  useEffect(() => { void refresh(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [search, departmentFilter, projectFilter, contractFilter, sensitiveFilter]);

  const visibleContracts = useMemo(() => contracts.filter((contract) => !form?.project_id || contract.project_id === form.project_id), [contracts, form?.project_id]);

  function openCreate() {
    setForm({ ...blankForm, department_id: departments[0]?.id ?? "", owner_id: adminId ?? "" });
  }

  async function openEdit(item: DocumentItem) {
    try {
      const detail: DocumentDetail = await getDocument(item.id);
      setForm({ id: detail.id, department_id: detail.department_id, title: detail.title, category: detail.category, sensitive: detail.sensitive, content: detail.content, owner_id: detail.owner_id ?? "", project_id: detail.project_id ?? "", contract_id: detail.contract_id ?? "" });
    } catch (loadError) { setError(errorMessage(loadError)); }
  }

  async function save() {
    if (!form || !form.department_id || !form.title.trim() || !form.content.trim()) { setError("请填写部门、标题和文档内容"); return; }
    setSaving(true); setError("");
    try {
      const relation = { project_id: form.project_id || null, contract_id: form.contract_id || null };
      if (form.id) await updateDocument(form.id, { title: form.title.trim(), category: form.category.trim(), sensitive: form.sensitive, content: form.content, owner_id: form.owner_id || null, ...relation });
      else await createDocument(form.department_id, { title: form.title.trim(), category: form.category.trim(), sensitive: form.sensitive, content: form.content, owner_id: form.owner_id || undefined, ...relation });
      setForm(null); await refresh();
    } catch (saveError) { setError(errorMessage(saveError)); }
    finally { setSaving(false); }
  }

  async function remove(item: DocumentItem) {
    if (!window.confirm(`确认删除文档「${item.title}」？`)) return;
    try { await deleteDocument(item.id); await refresh(); } catch (deleteError) { setError(errorMessage(deleteError)); }
  }

  return (
    <div className="mx-auto w-full max-w-6xl">
      <div className="flex flex-wrap items-start justify-between gap-4"><div><h2 className="text-lg font-semibold text-slate-900">知识文档</h2><p className="mt-1 text-sm text-slate-400">按部门、项目和合同追踪知识资料；未归属项目的文档仍可独立检索。</p></div><button onClick={openCreate} className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500">新建文档</button></div>
      {error && <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}
      <div className="mt-4 grid gap-3 md:grid-cols-6"><input className="rounded-md border border-slate-300 px-3 py-2 text-sm md:col-span-2" placeholder="搜索标题或分类" value={search} onChange={(e) => setSearch(e.target.value)} /><select className="rounded-md border border-slate-300 px-3 py-2 text-sm" value={departmentFilter} onChange={(e) => setDepartmentFilter(e.target.value)}><option value="">全部部门</option>{departments.map((dept) => <option key={dept.id} value={dept.id}>{dept.name}</option>)}</select><select className="rounded-md border border-slate-300 px-3 py-2 text-sm" value={projectFilter} onChange={(e) => { setProjectFilter(e.target.value); setContractFilter(""); }}><option value="">全部项目</option>{projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}</select><select className="rounded-md border border-slate-300 px-3 py-2 text-sm" value={contractFilter} onChange={(e) => setContractFilter(e.target.value)}><option value="">全部合同</option>{contracts.filter((contract) => !projectFilter || contract.project_id === projectFilter).map((contract) => <option key={contract.id} value={contract.id}>{contract.name}</option>)}</select><select className="rounded-md border border-slate-300 px-3 py-2 text-sm" value={sensitiveFilter} onChange={(e) => setSensitiveFilter(e.target.value)}><option value="">全部敏感性</option><option value="true">敏感</option><option value="false">普通</option></select></div>
      {loading ? <p className="mt-6 text-sm text-slate-400">加载中...</p> : <div className="mt-4 overflow-x-auto rounded-lg border border-slate-200 bg-white"><table className="w-full text-sm"><thead className="bg-slate-50 text-left text-xs text-slate-400"><tr><th className="px-4 py-3">文档</th><th className="px-4 py-3">部门</th><th className="px-4 py-3">项目</th><th className="px-4 py-3">合同</th><th className="px-4 py-3">状态</th><th className="px-4 py-3" /></tr></thead><tbody>{documents.map((item) => <tr key={item.id} className="border-t border-slate-100 hover:bg-slate-50"><td className="px-4 py-3"><button onClick={() => void openEdit(item)} className="text-left"><div className="font-medium text-slate-800 hover:text-indigo-700">{item.title}</div><div className="text-xs text-slate-400">{item.category || "未分类"}</div></button></td><td className="px-4 py-3 text-slate-600">{departments.find((dept) => dept.id === item.department_id)?.name ?? item.department_id}</td><td className="px-4 py-3 text-slate-600">{item.project_name || "未归属项目"}</td><td className="px-4 py-3 text-slate-600">{item.contract_name || "—"}</td><td className="px-4 py-3 text-slate-600">{item.sensitive ? "敏感" : "普通"}</td><td className="px-4 py-3 text-right"><button onClick={() => void remove(item)} className="text-red-400 hover:text-red-600">删除</button></td></tr>)}</tbody></table>{documents.length === 0 && <p className="px-4 py-10 text-center text-sm text-slate-400">暂无知识文档</p>}</div>}

      {form && <div className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-black/30 p-6" onClick={() => setForm(null)}><div className="my-auto w-full max-w-2xl rounded-xl bg-white p-6 shadow-xl" onClick={(event) => event.stopPropagation()}><h2 className="mb-5 text-xl font-semibold text-slate-900">{form.id ? "编辑文档" : "新建文档"}</h2><div className="grid gap-4 md:grid-cols-2"><label className="text-sm text-slate-600">所属部门<select disabled={Boolean(form.id)} className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" value={form.department_id} onChange={(e) => setForm({ ...form, department_id: e.target.value })}>{departments.map((dept) => <option key={dept.id} value={dept.id}>{dept.name}</option>)}</select></label><label className="text-sm text-slate-600">所属人<select className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" value={form.owner_id} onChange={(e) => setForm({ ...form, owner_id: e.target.value })}><option value="">未指定</option>{owners.map((owner) => <option key={owner.id} value={owner.id}>{owner.username}</option>)}</select></label><label className="text-sm text-slate-600">项目<select className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" value={form.project_id} onChange={(e) => setForm({ ...form, project_id: e.target.value, contract_id: "" })}><option value="">未归属项目</option>{projects.map((project) => <option key={project.id} value={project.id}>{project.name}（{project.code}）</option>)}</select></label><label className="text-sm text-slate-600">合同<select className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" value={form.contract_id} onChange={(e) => setForm({ ...form, contract_id: e.target.value })}><option value="">未关联合同</option>{visibleContracts.map((contract) => <option key={contract.id} value={contract.id}>{contract.name}（{contract.code}）</option>)}</select></label><input className="rounded-md border border-slate-300 px-3 py-2 text-sm" placeholder="标题" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /><input className="rounded-md border border-slate-300 px-3 py-2 text-sm" placeholder="分类（可选）" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} /></div><label className="mt-4 flex items-center gap-2 text-sm text-slate-600"><input type="checkbox" checked={form.sensitive} onChange={(e) => setForm({ ...form, sensitive: e.target.checked })} />标记为敏感文档</label><textarea className="mt-4 h-64 w-full rounded-md border border-slate-300 px-3 py-2 text-sm font-mono" placeholder="文档内容" value={form.content} onChange={(e) => setForm({ ...form, content: e.target.value })} />{error && <p className="mt-3 text-sm text-red-600">{error}</p>}<div className="mt-5 flex justify-end gap-2"><button onClick={() => setForm(null)} className="px-4 py-2 text-sm text-slate-500 hover:bg-slate-100">取消</button><button onClick={() => void save()} disabled={saving} className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">{saving ? "保存中..." : "保存"}</button></div></div></div>}
    </div>
  );
}
