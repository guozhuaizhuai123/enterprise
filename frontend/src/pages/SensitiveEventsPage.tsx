import { useEffect, useState } from "react";
import {
  createSensitiveKeyword,
  deleteSensitiveEvent,
  deleteSensitiveKeyword,
  listSensitiveEvents,
  listSensitiveKeywords,
  updateSensitiveKeyword,
} from "../api/admin";
import type { SensitiveEvent, SensitiveKeyword } from "../types";

type Tab = "events" | "keywords";

export default function SensitiveEventsPage() {
  const [tab, setTab] = useState<Tab>("events");
  const [events, setEvents] = useState<SensitiveEvent[]>([]);
  const [keywords, setKeywords] = useState<SensitiveKeyword[]>([]);
  const [loading, setLoading] = useState(true);
  const [newKeyword, setNewKeyword] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingValue, setEditingValue] = useState("");
  // 「不提示」：勾选后删除敏感词不再弹确认框，直接删除（不禁用删除本身）。
  const [skipDeleteConfirm, setSkipDeleteConfirm] = useState(false);

  async function refresh() {
    setLoading(true);
    try {
      const [eventData, keywordData] = await Promise.all([listSensitiveEvents(), listSensitiveKeywords()]);
      setEvents(eventData);
      setKeywords(keywordData);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function handleDeleteEvent(eventId: string) {
    if (!confirm("确定删除这条敏感话题记录？")) return;
    await deleteSensitiveEvent(eventId);
    await refresh();
  }

  async function handleCreateKeyword(event: React.FormEvent) {
    event.preventDefault();
    if (!newKeyword.trim()) return;
    await createSensitiveKeyword(newKeyword.trim());
    setNewKeyword("");
    await refresh();
  }

  async function handleToggleKeyword(item: SensitiveKeyword) {
    await updateSensitiveKeyword(item.id, { enabled: !item.enabled });
    await refresh();
  }

  async function handleSaveKeyword(item: SensitiveKeyword) {
    if (!editingValue.trim()) return;
    await updateSensitiveKeyword(item.id, { keyword: editingValue.trim() });
    setEditingId(null);
    setEditingValue("");
    await refresh();
  }

  async function handleDeleteKeyword(item: SensitiveKeyword) {
    if (!skipDeleteConfirm && !confirm(`确定删除敏感词“${item.keyword}”？`)) return;
    await deleteSensitiveKeyword(item.id);
    await refresh();
  }

  return (
    <div className="mx-auto w-full max-w-6xl">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">敏感话题管理</h2>
          <p className="text-sm text-slate-400 mt-1">管理门禁词库并查看被拦截的问题。</p>
        </div>
        <div className="flex gap-1 border-b border-slate-200">
          <button onClick={() => setTab("events")} className={`px-3 py-2 text-sm ${tab === "events" ? "border-b-2 border-indigo-600 text-indigo-600 font-medium" : "text-slate-500"}`}>
            触发记录 ({events.length})
          </button>
          <button onClick={() => setTab("keywords")} className={`px-3 py-2 text-sm ${tab === "keywords" ? "border-b-2 border-indigo-600 text-indigo-600 font-medium" : "text-slate-500"}`}>
            敏感词 ({keywords.length})
          </button>
        </div>
      </div>

      {loading ? (
        <p className="text-sm text-slate-400">加载中...</p>
      ) : tab === "events" ? (
        events.length === 0 ? (
          <p className="text-sm text-slate-400">暂无敏感话题记录</p>
        ) : (
          <div className="overflow-x-auto bg-white rounded-lg border border-slate-200">
            <table className="w-full text-sm">
              <thead><tr className="text-left text-slate-400 border-b border-slate-100">
                <th className="px-4 py-3 font-medium whitespace-nowrap">时间</th>
                <th className="px-4 py-3 font-medium">提问人</th>
                <th className="px-4 py-3 font-medium">部门</th>
                <th className="px-4 py-3 font-medium min-w-72">提问内容</th>
                <th className="px-4 py-3 font-medium">命中关键词</th>
                <th className="px-4 py-3 font-medium min-w-64">处理原因</th>
                <th className="px-4 py-3 font-medium" />
              </tr></thead>
              <tbody>{events.map((event) => (
                <tr key={event.id} className="border-b border-slate-50 last:border-0 align-top">
                  <td className="px-4 py-3 text-slate-500 whitespace-nowrap">{new Date(event.created_at).toLocaleString()}</td>
                  <td className="px-4 py-3 text-slate-700 font-medium">{event.username}</td>
                  <td className="px-4 py-3 text-slate-500">{event.department_name}</td>
                  <td className="px-4 py-3 text-slate-700 whitespace-pre-wrap">{event.question}</td>
                  <td className="px-4 py-3 text-amber-600">{event.matched_keyword || "-"}</td>
                  <td className="px-4 py-3 text-slate-500">{event.reason}</td>
                  <td className="px-4 py-3 text-right"><button onClick={() => handleDeleteEvent(event.id)} className="text-xs text-red-400 hover:text-red-600">删除</button></td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )
      ) : (
        <div>
          <form onSubmit={handleCreateKeyword} className="flex gap-2 mb-4">
            <input className="rounded-md border border-slate-300 px-3 py-2 text-sm w-72" placeholder="新增敏感词" value={newKeyword} onChange={(event) => setNewKeyword(event.target.value)} />
            <button type="submit" className="rounded-md bg-indigo-600 text-white px-4 py-2 text-sm font-medium hover:bg-indigo-500">添加</button>
          </form>
          <label className="mb-3 flex w-fit items-center gap-2 text-xs text-slate-500">
            <input type="checkbox" checked={skipDeleteConfirm} onChange={(event) => setSkipDeleteConfirm(event.target.checked)} />
            删除时不提示确认（勾选后点删除直接生效）
          </label>
          <div className="bg-white rounded-lg border border-slate-200 divide-y divide-slate-100">
            {keywords.map((item) => (
              <div key={item.id} className="flex items-center gap-3 px-4 py-3">
                {editingId === item.id ? (
                  <input autoFocus className="rounded border border-slate-300 px-2 py-1 text-sm flex-1" value={editingValue} onChange={(event) => setEditingValue(event.target.value)} />
                ) : (
                  <span className={`flex-1 text-sm ${item.enabled ? "text-slate-700" : "text-slate-400 line-through"}`}>{item.keyword}</span>
                )}
                <button onClick={() => handleToggleKeyword(item)} className="text-xs text-slate-500 hover:text-indigo-600">{item.enabled ? "停用" : "启用"}</button>
                {editingId === item.id ? (
                  <button onClick={() => handleSaveKeyword(item)} className="text-xs text-indigo-600 hover:text-indigo-800">保存</button>
                ) : (
                  <button onClick={() => { setEditingId(item.id); setEditingValue(item.keyword); }} className="text-xs text-slate-500 hover:text-indigo-600">编辑</button>
                )}
                <button onClick={() => handleDeleteKeyword(item)} className="text-xs text-red-400 hover:text-red-600">删除</button>
              </div>
            ))}
            {keywords.length === 0 && <p className="px-4 py-5 text-sm text-slate-400">暂无敏感词</p>}
          </div>
        </div>
      )}
    </div>
  );
}
