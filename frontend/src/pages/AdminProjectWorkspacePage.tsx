import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getProjectWorkspace } from "../api/projects";
import type { ProjectWorkspace } from "../types";

type WorkspaceTab = "overview" | "contracts" | "documents";

const PROJECT_STATUS: Record<string, string> = {
  preparing: "筹备中",
  active: "进行中",
  closed: "已结项",
  paused: "已暂停",
  cancelled: "已取消",
};

const CONTRACT_STATUS: Record<string, string> = {
  draft: "草稿",
  reviewing: "审批中",
  active: "已生效",
  fulfilled: "已履行",
  expired: "已到期",
  terminated: "已终止",
};

export default function AdminProjectWorkspacePage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [workspace, setWorkspace] = useState<ProjectWorkspace | null>(null);
  const [tab, setTab] = useState<WorkspaceTab>("overview");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!projectId) return;
    setLoading(true);
    getProjectWorkspace(projectId)
      .then(setWorkspace)
      .catch(() => setError("项目工作台加载失败，请稍后重试"))
      .finally(() => setLoading(false));
  }, [projectId]);

  if (loading) return <p className="mx-auto w-full max-w-6xl text-sm text-slate-400">加载中...</p>;
  if (!workspace) {
    return <div className="mx-auto w-full max-w-6xl"><p className="text-sm text-red-600">{error || "项目不存在"}</p><Link to="/admin/projects" className="mt-3 inline-block text-sm text-indigo-600">返回项目列表</Link></div>;
  }

  const { project, contracts, documents } = workspace;
  const tabs: Array<{ id: WorkspaceTab; label: string; count?: number }> = [
    { id: "overview", label: "概览" },
    { id: "contracts", label: "合同", count: contracts.length },
    { id: "documents", label: "知识文档", count: documents.length },
  ];

  return (
    <div className="mx-auto w-full max-w-6xl">
      <Link to="/admin/projects" className="text-sm text-slate-400 hover:text-slate-600">← 返回项目工作台</Link>
      <div className="mt-3 flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs text-slate-400">{project.code}</p>
          <h2 className="mt-1 text-xl font-semibold text-slate-900">{project.name}</h2>
          <p className="mt-2 max-w-2xl text-sm text-slate-500">{project.description || "暂无项目说明"}</p>
        </div>
        <Link to="/admin/contracts" className="text-sm text-indigo-600 hover:text-indigo-800">打开合同台账</Link>
      </div>

      <div className="mt-6 grid grid-cols-2 gap-3 md:grid-cols-4">
        <div className="rounded-lg border border-slate-200 bg-white p-4"><p className="text-xs text-slate-400">项目状态</p><p className="mt-1 font-medium text-slate-800">{PROJECT_STATUS[project.status] ?? project.status}</p></div>
        <div className="rounded-lg border border-slate-200 bg-white p-4"><p className="text-xs text-slate-400">负责人</p><p className="mt-1 font-medium text-slate-800">{project.manager_name || "未设置"}</p></div>
        <div className="rounded-lg border border-slate-200 bg-white p-4"><p className="text-xs text-slate-400">关联合同</p><p className="mt-1 font-medium text-slate-800">{contracts.length} 份</p></div>
        <div className="rounded-lg border border-slate-200 bg-white p-4"><p className="text-xs text-slate-400">知识文档</p><p className="mt-1 font-medium text-slate-800">{documents.length} 份</p></div>
      </div>

      <div className="mt-6 flex gap-1 border-b border-slate-200">
        {tabs.map((item) => (
          <button key={item.id} onClick={() => setTab(item.id)} className={`px-4 py-2 text-sm ${tab === item.id ? "border-b-2 border-indigo-600 font-medium text-indigo-600" : "text-slate-500 hover:text-slate-700"}`}>
            {item.label}{item.count !== undefined && <span className="ml-1 text-xs text-slate-400">({item.count})</span>}
          </button>
        ))}
      </div>

      {tab === "overview" && (
        <div className="mt-5 rounded-lg border border-slate-200 bg-white p-5 text-sm text-slate-600">
          <dl className="grid gap-4 md:grid-cols-3">
            <div><dt className="text-xs text-slate-400">所属部门</dt><dd className="mt-1">{project.department_name || "未设置"}</dd></div>
            <div><dt className="text-xs text-slate-400">开始日期</dt><dd className="mt-1">{project.start_date || "未设置"}</dd></div>
            <div><dt className="text-xs text-slate-400">结束日期</dt><dd className="mt-1">{project.end_date || "未设置"}</dd></div>
            <div><dt className="text-xs text-slate-400">预算</dt><dd className="mt-1">{project.budget ? `¥${project.budget}` : "未设置"}</dd></div>
            <div><dt className="text-xs text-slate-400">项目类型</dt><dd className="mt-1">{project.type}</dd></div>
          </dl>
        </div>
      )}

      {tab === "contracts" && (
        <div className="mt-5 overflow-x-auto rounded-lg border border-slate-200 bg-white">
          <table className="w-full text-sm"><thead className="bg-slate-50 text-left text-xs text-slate-400"><tr><th className="px-4 py-3">合同</th><th className="px-4 py-3">类型</th><th className="px-4 py-3">状态</th><th className="px-4 py-3">签约方</th><th className="px-4 py-3">金额</th></tr></thead>
            <tbody>{contracts.map((contract) => <tr key={contract.id} className="border-t border-slate-100"><td className="px-4 py-3"><div className="font-medium text-slate-800">{contract.name}</div><div className="text-xs text-slate-400">{contract.code}</div></td><td className="px-4 py-3 text-slate-600">{contract.type}</td><td className="px-4 py-3 text-slate-600">{CONTRACT_STATUS[contract.status] ?? contract.status}</td><td className="px-4 py-3 text-slate-600">{contract.party_a || "—"} / {contract.party_b || "—"}</td><td className="px-4 py-3 text-slate-600">{contract.amount ? `${contract.currency} ${contract.amount}` : "—"}</td></tr>)}</tbody>
          </table>
          {contracts.length === 0 && <p className="px-4 py-8 text-center text-sm text-slate-400">暂无关联合同</p>}
        </div>
      )}

      {tab === "documents" && (
        <div className="mt-5 overflow-x-auto rounded-lg border border-slate-200 bg-white">
          <table className="w-full text-sm"><thead className="bg-slate-50 text-left text-xs text-slate-400"><tr><th className="px-4 py-3">文档</th><th className="px-4 py-3">部门</th><th className="px-4 py-3">合同</th><th className="px-4 py-3">敏感性</th><th className="px-4 py-3">更新时间</th></tr></thead>
            <tbody>{documents.map((document) => <tr key={document.id} className="border-t border-slate-100"><td className="px-4 py-3"><div className="font-medium text-slate-800">{document.title}</div><div className="text-xs text-slate-400">{document.category || "未分类"}</div></td><td className="px-4 py-3 text-slate-600">{document.department_id}</td><td className="px-4 py-3 text-slate-600">{document.contract_name || "未关联合同"}</td><td className="px-4 py-3 text-slate-600">{document.sensitive ? "敏感" : "普通"}</td><td className="px-4 py-3 text-slate-500">{new Date(document.updated_at).toLocaleString()}</td></tr>)}</tbody>
          </table>
          {documents.length === 0 && <p className="px-4 py-8 text-center text-sm text-slate-400">暂无项目知识文档</p>}
        </div>
      )}
    </div>
  );
}
