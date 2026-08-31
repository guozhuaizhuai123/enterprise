import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  createContract,
  deleteContract,
  listContracts,
  listProjects,
  updateContract,
} from "../api/projects";
import type {
  Contract,
  ContractInput,
  ContractStatus,
  ContractType,
  Project,
} from "../types";

const TYPE_LABELS: Record<ContractType, string> = {
  purchase: "采购合同",
  sales: "销售合同",
  service: "服务合同",
  lease: "租赁合同",
  nda: "保密协议",
  other: "其他",
};

const STATUS_LABELS: Record<ContractStatus, string> = {
  draft: "草稿",
  reviewing: "审批中",
  active: "已生效",
  fulfilled: "已履行",
  expired: "已到期",
  terminated: "已终止",
};

function errorMessage(error: unknown): string {
  const detail = (error as { response?: { data?: { detail?: string } } }).response?.data?.detail;
  return detail || "操作失败，请稍后重试";
}

export default function AdminContractsPage() {
  const [items, setItems] = useState<Contract[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<ContractStatus | "">("");

  const [editorOpen, setEditorOpen] = useState(false);
  const [selected, setSelected] = useState<Contract | null>(null);
  const [form, setForm] = useState<ContractInput>({
    code: "",
    name: "",
    type: "purchase",
    status: "draft",
    project_id: null,
    party_a: "",
    party_b: "",
    amount: null,
    currency: "CNY",
    sign_date: null,
    effective_date: null,
    expiry_date: null,
    owner_id: null,
    description: "",
  });

  async function refresh() {
    setLoading(true);
    setError("");
    try {
      const params: Record<string, string> = {};
      if (statusFilter) params.status = statusFilter;
      if (search.trim()) params.q = search.trim();
      const [contracts, projectList] = await Promise.all([
        listContracts(params),
        listProjects(),
      ]);
      setItems(contracts);
      setProjects(projectList);
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
        item.code.toLowerCase().includes(keyword) ||
        item.party_a.toLowerCase().includes(keyword) ||
        item.party_b.toLowerCase().includes(keyword),
    );
  }, [items, search]);

  function openCreate() {
    setSelected(null);
    setForm({
      code: "",
      name: "",
      type: "purchase",
      status: "draft",
      project_id: null,
      party_a: "",
      party_b: "",
      amount: null,
      currency: "CNY",
      sign_date: null,
      effective_date: null,
      expiry_date: null,
      owner_id: null,
      description: "",
    });
    setEditorOpen(true);
  }

  function openEdit(item: Contract) {
    setSelected(item);
    setForm({
      code: item.code,
      name: item.name,
      type: item.type,
      status: item.status,
      project_id: item.project_id,
      party_a: item.party_a,
      party_b: item.party_b,
      amount: item.amount,
      currency: item.currency,
      sign_date: item.sign_date,
      effective_date: item.effective_date,
      expiry_date: item.expiry_date,
      owner_id: item.owner_id,
      description: item.description,
    });
    setEditorOpen(true);
  }

  async function save() {
    if (!form.code.trim() || !form.name.trim()) {
      setError("请填写合同编号与名称");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const payload: ContractInput = {
        ...form,
        amount: form.amount && form.amount.trim() !== "" ? form.amount.trim() : null,
      };
      if (selected) {
        await updateContract(selected.id, payload);
      } else {
        await createContract(payload);
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

  async function remove(item: Contract) {
    if (!window.confirm(`确认删除合同「${item.name}」？`)) return;
    setBusy(true);
    setError("");
    try {
      await deleteContract(item.id);
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
          <h2 className="text-lg font-semibold text-slate-900">合同管理</h2>
          <p className="mt-1 text-sm text-slate-400">合同为独立法律实体，可归属到项目（弱引用）。</p>
        </div>
        <button
          onClick={openCreate}
          className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500"
        >
          新建合同
        </button>
      </div>

      {error && <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}

      <div className="mt-4 flex flex-wrap gap-3">
        <input
          className="min-w-56 flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm"
          placeholder="搜索合同编号 / 名称 / 签约方"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select
          className="rounded-md border border-slate-300 px-3 py-2 text-sm"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as ContractStatus | "")}
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
        <p className="mt-6 text-sm text-slate-400">暂无合同</p>
      ) : (
        <div className="mt-4 overflow-x-auto rounded-xl border border-slate-200 bg-white">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs font-medium uppercase tracking-wide text-slate-400">
              <tr>
                <th className="px-4 py-3">编号 / 名称</th>
                <th className="px-4 py-3">类型</th>
                <th className="px-4 py-3">状态</th>
                <th className="px-4 py-3">归属项目</th>
                <th className="px-4 py-3">金额</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {visible.map((item) => (
                <tr key={item.id} className="border-t border-slate-100 hover:bg-slate-50">
                  <td className="px-4 py-3">
                    <div className="font-medium text-slate-800">{item.name}</div>
                    <div className="text-xs text-slate-400">{item.code}</div>
                  </td>
                  <td className="px-4 py-3 text-slate-600">{TYPE_LABELS[item.type]}</td>
                  <td className="px-4 py-3">
                    <span className="rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-600">{STATUS_LABELS[item.status]}</span>
                  </td>
                  <td className="px-4 py-3 text-slate-500">{item.project_id ? <Link to={`/admin/projects/${item.project_id}`} className="text-indigo-600 hover:text-indigo-800">{item.project_name || "查看项目"}</Link> : "未归属项目"}</td>
                  <td className="px-4 py-3 text-slate-600">{item.amount ? `${item.currency} ${item.amount}` : "—"}</td>
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
            <h2 className="mb-5 text-xl font-semibold text-slate-900">{selected ? "编辑合同" : "新建合同"}</h2>
            <div className="grid grid-cols-2 gap-4">
              <label className="text-sm text-slate-600">
                合同编号
                <input className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} placeholder="如 CTR-2026-001" />
              </label>
              <label className="text-sm text-slate-600">
                合同名称
                <input className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
              </label>
              <label className="text-sm text-slate-600">
                类型
                <select className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value as ContractType })}>
                  {Object.entries(TYPE_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </label>
              <label className="text-sm text-slate-600">
                状态
                <select className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value as ContractStatus })}>
                  {Object.entries(STATUS_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </label>
              <label className="col-span-2 text-sm text-slate-600">
                归属项目（可选）
                <select className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" value={form.project_id ?? ""} onChange={(e) => setForm({ ...form, project_id: e.target.value || null })}>
                  <option value="">不归属项目</option>
                  {projects.map((project) => (
                    <option key={project.id} value={project.id}>{project.name}（{project.code}）</option>
                  ))}
                </select>
              </label>
              <label className="text-sm text-slate-600">
                甲方
                <input className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" value={form.party_a} onChange={(e) => setForm({ ...form, party_a: e.target.value })} />
              </label>
              <label className="text-sm text-slate-600">
                乙方
                <input className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" value={form.party_b} onChange={(e) => setForm({ ...form, party_b: e.target.value })} />
              </label>
              <label className="text-sm text-slate-600">
                金额
                <input className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" value={form.amount ?? ""} onChange={(e) => setForm({ ...form, amount: e.target.value || null })} placeholder="选填" />
              </label>
              <label className="text-sm text-slate-600">
                币种
                <input className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value })} />
              </label>
              <label className="text-sm text-slate-600">
                签订日期
                <input type="date" className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" value={form.sign_date ?? ""} onChange={(e) => setForm({ ...form, sign_date: e.target.value || null })} />
              </label>
              <label className="text-sm text-slate-600">
                生效日期
                <input type="date" className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" value={form.effective_date ?? ""} onChange={(e) => setForm({ ...form, effective_date: e.target.value || null })} />
              </label>
              <label className="text-sm text-slate-600">
                到期日期
                <input type="date" className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" value={form.expiry_date ?? ""} onChange={(e) => setForm({ ...form, expiry_date: e.target.value || null })} />
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
