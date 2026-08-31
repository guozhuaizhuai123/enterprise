import { useEffect, useState } from "react";
import {
  createUserMemory,
  deleteUserMemory,
  getChatSettings,
  listUserMemories,
  updateChatSettings,
  updateUserMemory,
} from "../api/memory";
import type { MemoryItem, MemoryLevel } from "../types";

type Form = { id: string | null; title: string; content: string; enabled: boolean };
const blank: Form = { id: null, title: "", content: "", enabled: true };

export default function UserMemoryDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [items, setItems] = useState<MemoryItem[]>([]);
  const [form, setForm] = useState<Form | null>(null);
  const [level, setLevel] = useState<MemoryLevel>(3);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function refresh() {
    setLoading(true); setError("");
    try { const [memories, settings] = await Promise.all([listUserMemories(), getChatSettings()]); setItems(memories); setLevel(settings.default_memory_level); }
    catch { setError("加载记忆失败，请稍后重试"); }
    finally { setLoading(false); }
  }
  useEffect(() => { if (open) void refresh(); else setForm(null); }, [open]);

  async function save() {
    if (!form || !form.title.trim() || !form.content.trim()) { setError("标题和内容不能为空"); return; }
    setSaving(true); setError("");
    try {
      if (form.id) await updateUserMemory(form.id, { title: form.title.trim(), content: form.content.trim(), enabled: form.enabled });
      else await createUserMemory({ title: form.title.trim(), content: form.content.trim(), enabled: form.enabled });
      setForm(null); await refresh();
    } catch (e: any) { setError(e?.response?.data?.detail || "保存失败，请稍后重试"); }
    finally { setSaving(false); }
  }
  async function remove(item: MemoryItem) {
    if (!confirm(`确定删除记忆“${item.title}”？`)) return;
    try { await deleteUserMemory(item.id); await refresh(); } catch { setError("删除失败，请稍后重试"); }
  }
  async function changeLevel(next: MemoryLevel) {
    setLevel(next); setError("");
    try { await updateChatSettings({ default_memory_level: next }); } catch { setError("默认记忆级别保存失败"); }
  }
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" onClick={onClose}>
      <div className="w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-lg bg-white p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4"><h2 className="text-lg font-semibold text-slate-900">我的记忆</h2><button aria-label="关闭" onClick={onClose} className="text-xl text-slate-400 hover:text-slate-700">×</button></div>
        <div className="mb-5"><p className="text-sm font-medium text-slate-700 mb-2">新会话默认记忆级别</p><div className="flex flex-wrap gap-2">{([1,2,3,4,5] as MemoryLevel[]).map((n) => <label key={n} className={`cursor-pointer rounded border px-3 py-1.5 text-xs ${level === n ? "border-indigo-600 bg-indigo-50 text-indigo-700" : "border-slate-200 text-slate-500"}`}><input className="sr-only" type="radio" checked={level === n} onChange={() => void changeLevel(n)} />{n} {(["极速","较快","均衡","深入","最深"] as string[])[n - 1]}</label>)}</div></div>
        <div className="flex items-center justify-between mb-2"><h3 className="text-sm font-medium text-slate-700">记忆条目 <span className="text-xs text-slate-400">{items.length} / 20</span></h3><button disabled={items.length >= 20 || !!form} onClick={() => setForm({ ...blank })} className="rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white disabled:opacity-40">＋ 新增</button></div>
        {loading ? <p className="text-sm text-slate-400 py-6">加载中...</p> : items.length === 0 && !form ? <p className="text-sm text-slate-400 py-6">暂无记忆条目</p> : <div className="divide-y divide-slate-100 border border-slate-200 rounded-md">{items.map((item) => <div key={item.id} className="p-3"><div className="flex items-start justify-between gap-3"><div className="min-w-0"><p className="font-medium text-sm text-slate-800">{item.title}</p><p className="text-sm text-slate-500 whitespace-pre-wrap break-words">{item.content}</p></div><div className="flex shrink-0 gap-2"><button aria-label="编辑" title="编辑" onClick={() => setForm({ id: item.id, title: item.title, content: item.content, enabled: item.enabled })} className="text-slate-400 hover:text-indigo-600">✎</button><button aria-label="删除" title="删除" onClick={() => void remove(item)} className="text-slate-400 hover:text-red-600">⌫</button></div></div><label className="mt-2 inline-flex items-center gap-2 text-xs text-slate-500"><input type="checkbox" checked={item.enabled} onChange={(e) => void updateUserMemory(item.id, { enabled: e.target.checked }).then(refresh).catch(() => setError("状态保存失败"))} />启用</label></div>)}</div>}
        {form && <div className="mt-3 rounded-md border border-indigo-100 bg-indigo-50/40 p-3"><div className="flex gap-2"><input autoFocus className="min-w-0 flex-1 rounded border border-slate-300 px-2 py-1.5 text-sm" placeholder="标题" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /><span className="self-center text-xs text-slate-400">{form.title.length}</span></div><textarea className="mt-2 w-full rounded border border-slate-300 px-2 py-1.5 text-sm" rows={3} placeholder="内容" maxLength={500} value={form.content} onChange={(e) => setForm({ ...form, content: e.target.value })} /><div className="flex items-center justify-between mt-1"><label className="text-xs text-slate-500"><input type="checkbox" checked={form.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} /> <span className="ml-1">启用</span></label><span className="text-xs text-slate-400">{form.content.length} / 500</span></div><div className="flex justify-end gap-2 mt-3"><button onClick={() => setForm(null)} className="px-3 py-1.5 text-xs text-slate-500">取消</button><button disabled={saving} onClick={() => void save()} className="rounded bg-indigo-600 px-3 py-1.5 text-xs text-white disabled:opacity-50">{saving ? "保存中..." : "保存"}</button></div></div>}
        {error && <p className="mt-3 text-sm text-red-500">{error}</p>}
      </div>
    </div>
  );
}
