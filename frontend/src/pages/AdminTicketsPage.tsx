import { useEffect, useMemo, useRef, useState } from "react";
import { useAuthStore } from "../store/auth";
import {
  addTicketMessage, createAdminTodo, dispatchAdminTicket, listAdminTicketMessages, listAdminTickets,
  listAdminTodos, listTicketEvents, listUsers, ticketAction, updateAdminTodo,
} from "../api/tickets";
import type { Ticket, TicketEvent, TicketMessage, Todo, UserOption } from "../types";
import { usePolling } from "../hooks/usePolling";

const labels: Record<string, string> = { same_department: "同部门协助", cross_department: "跨部门协助", question: "业务询问", issue: "问题反馈" };
const statuses: Record<string, string> = { pending_acceptance: "待接收", pending_admin: "待管理员审批", in_progress: "处理中", answered: "已回复", completed: "已完成", rejected: "已拒绝", closed: "已关闭", cancelled: "已撤回" };
const FINISHED = new Set(["completed", "closed", "cancelled", "rejected"]);

/** 状态徽标：按当前状态着色，一眼区分待办优先级。 */
const statusTone: Record<string, string> = {
  pending_acceptance: "bg-amber-50 text-amber-700 border-amber-200",
  pending_admin: "bg-violet-50 text-violet-700 border-violet-200",
  in_progress: "bg-blue-50 text-blue-700 border-blue-200",
  answered: "bg-teal-50 text-teal-700 border-teal-200",
  completed: "bg-emerald-50 text-emerald-700 border-emerald-200",
  rejected: "bg-slate-100 text-slate-500 border-slate-200",
  closed: "bg-slate-100 text-slate-500 border-slate-200",
  cancelled: "bg-slate-100 text-slate-500 border-slate-200",
};

function StatusPill({ status }: { status: string }) {
  return (
    <span className={`inline-flex shrink-0 items-center rounded-full border px-2.5 py-0.5 text-[11px] font-medium ${statusTone[status] ?? "bg-slate-100 text-slate-500 border-slate-200"}`}>
      {statuses[status] ?? status}
    </span>
  );
}

const eventTypeLabels: Record<string, string> = {
  created: "创建工单", dispatched: "派发", accept: "接收", reject: "拒绝", approve: "批准",
  admin_reject: "驳回", "admin-reject": "驳回", close: "关闭", complete: "完成", reopen: "重新打开",
  message_added: "新增回复", todo_created: "生成待办", todo_updated: "更新待办",
};

export default function AdminTicketsPage() {
  const { userId } = useAuthStore();
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [events, setEvents] = useState<TicketEvent[]>([]);
  const [users, setUsers] = useState<UserOption[]>([]);
  const [todos, setTodos] = useState<Todo[]>([]);
  const [assignee, setAssignee] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [notice, setNotice] = useState("");
  // 沟通记录弹窗：selected 为当前查看的工单
  const [selected, setSelected] = useState<Ticket | null>(null);
  const [messages, setMessages] = useState<TicketMessage[]>([]);
  const [reply, setReply] = useState("");
  const [sending, setSending] = useState(false);
  const [draft, setDraft] = useState<Record<string, string>>({});

  const selectedRef = useRef<Ticket | null>(null);
  useEffect(() => { selectedRef.current = selected; }, [selected]);

  async function refresh() {
    try {
      const [t, e, u, d] = await Promise.all([listAdminTickets(), listTicketEvents(), listUsers(), listAdminTodos()]);
      setTickets(t); setEvents(e); setUsers(u); setTodos(d);
      const cur = selectedRef.current;
      if (cur) {
        const updated = t.find((x) => x.id === cur.id) ?? null;
        selectedRef.current = updated;
        setSelected(updated);
        setMessages(await listAdminTicketMessages(cur.id).catch(() => []));
      }
    } catch {
      // 单次拉取失败保留上一次数据，下一轮自动重试。
    }
  }

  // 自动刷新改为静默轮询，不在页面上展示刷新控件。
  usePolling(() => refresh(), { interval: 10_000 });

  useEffect(() => {
    void refresh();
    // Initial route hydration only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 按「协助部门 → 具体个人」分组；一人属于多部门时会出现在多个分组下
  const employeesByDept = useMemo(() => {
    const map = new Map<string, UserOption[]>();
    users.filter((u) => u.role === "employee").forEach((u) => {
      const keys = u.departments?.length ? u.departments : [u.department_name?.trim() || "未分配部门"];
      new Set(keys.map((k) => k.trim() || "未分配部门")).forEach((key) => {
        if (!map.has(key)) map.set(key, []);
        map.get(key)!.push(u);
      });
    });
    return [...map.entries()].sort((a, b) => a[0].localeCompare(b[0], "zh"));
  }, [users]);

  async function action(id: string, name: string) {
    await ticketAction(id, name);
    setNotice(name === "approve" ? "已批准并生成待办" : name === "complete" ? "工单已标记完成" : "操作已完成");
    await refresh();
  }
  async function dispatchTicket(t: Ticket) {
    const who = draft[t.id];
    if (!who) return;
    try {
      await dispatchAdminTicket(t.id, who);
      setNotice("已派发协助人");
      setDraft((d) => ({ ...d, [t.id]: "" }));
      await refresh();
    } catch { setNotice("派发失败，请重试"); }
  }
  async function dispatch(e: React.FormEvent) {
    e.preventDefault();
    if (!assignee || !title.trim()) return;
    await createAdminTodo({ assignee_id: assignee, title, description });
    setTitle(""); setDescription(""); setNotice("待办已分发");
    await refresh();
  }
  function openConversation(t: Ticket) {
    setSelected(t); setReply("");
    void listAdminTicketMessages(t.id).then(setMessages).catch(() => setMessages([]));
  }
  function closeConversation() {
    setSelected(null); setMessages([]); setReply("");
  }
  async function sendReply(e: React.FormEvent) {
    e.preventDefault();
    if (!selected || !reply.trim()) return;
    setSending(true);
    try {
      await addTicketMessage(selected.id, reply);
      setReply("");
      setMessages(await listAdminTicketMessages(selected.id));
    } catch {
      setNotice("回复发送失败，请重试");
    } finally {
      setSending(false);
    }
  }

  // 布局原则：左边 = 未完成（待处理工单 + 未完成待办），右边 = 历史（已完成/已取消）。
  const activeTickets = tickets.filter((t) => !FINISHED.has(t.status));
  const finishedTickets = tickets.filter((t) => FINISHED.has(t.status));
  const openTodos = todos.filter((t) => t.status === "pending" || t.status === "in_progress");
  const doneTodos = todos.filter((t) => t.status === "completed" || t.status === "cancelled");

  async function setTodoStatus(id: string, status: string) {
    try {
      await updateAdminTodo(id, status);
      await refresh();
    } catch {
      setNotice("待办状态更新失败，请重试");
    }
  }

  return (
    <div className="mx-auto w-full max-w-7xl">
      <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">工单与待办</h2>
          <p className="text-sm text-slate-500 mt-1">左侧集中处理未完成事项，右侧是分发入口与历史记录</p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          {notice && (
            <span className="rounded-md bg-emerald-50 px-2.5 py-1 text-sm text-emerald-700">{notice}</span>
          )}
        </div>
      </div>

      <div className="grid gap-5 xl:grid-cols-[1fr_340px]">
        {/* 左列：未完成事项 */}
        <div className="space-y-5">
          <section className="bg-white border border-slate-200 rounded-xl p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-slate-900">工单处理</h3>
              <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs text-slate-500">未完成 {activeTickets.length} 条</span>
            </div>
            <div className="space-y-3">
              {activeTickets.map((t) => {
                // 派发候选：排除发起人自己；若指定了协助部门，则只列出该部门的人
                const candidates = users.filter((u) => u.role === "employee"
                  && u.id !== t.requester_id
                  && (!t.requested_department_id || (u.department_ids ?? []).includes(t.requested_department_id)));
                return (
                  <div key={t.id} className="rounded-lg border border-slate-200 p-4 hover:border-indigo-200 transition">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-sm font-medium text-slate-900">{t.subject}</span>
                          <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-500">{labels[t.ticket_type]}</span>
                        </div>
                        <div className="text-xs text-slate-500 mt-1">
                          发起人 {t.requester_name} → 处理人 {t.target_user_name || "未派发"}
                          {t.requested_department_id && (
                            <span className="text-indigo-600"> · 协助部门 {t.requested_department_name}</span>
                          )}
                        </div>
                      </div>
                      <StatusPill status={t.status} />
                    </div>
                    <p className="text-sm text-slate-600 mt-2 line-clamp-3 whitespace-pre-wrap">{t.description}</p>

                    <div className="flex flex-wrap gap-2 mt-3">
                      {t.status === "pending_admin" && <button onClick={() => void action(t.id, "approve")} className="rounded-md bg-emerald-600 text-white px-3 py-1.5 text-xs font-medium hover:bg-emerald-500">批准</button>}
                      {t.status === "pending_admin" && <button onClick={() => void action(t.id, "admin-reject")} className="rounded-md border border-slate-300 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50">驳回</button>}
                      {t.status === "pending_acceptance" && t.target_user_id === userId && <button onClick={() => void action(t.id, "accept")} className="rounded-md bg-emerald-600 text-white px-3 py-1.5 text-xs font-medium hover:bg-emerald-500">接收</button>}
                      <button onClick={() => void action(t.id, "complete")} className="rounded-md bg-indigo-600 text-white px-3 py-1.5 text-xs font-medium hover:bg-indigo-500">已完成</button>
                      <button onClick={() => openConversation(t)} className="rounded-md border border-slate-300 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50">沟通记录</button>
                    </div>

                    <div className="flex gap-2 mt-3 items-center">
                      <select value={draft[t.id] ?? ""} onChange={(e) => setDraft((d) => ({ ...d, [t.id]: e.target.value }))}
                        className="flex-1 rounded-md border border-slate-300 px-2 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-indigo-500">
                        {t.requested_department_id ? (
                          <>
                            <option value="">派发给「{t.requested_department_name}」的同事</option>
                            {candidates.map((m) => <option key={m.id} value={m.id}>{m.username}</option>)}
                          </>
                        ) : (
                          <>
                            <option value="">派发协助：选择部门下的具体个人</option>
                            {employeesByDept.map(([dept, members]) => {
                              const scoped = members.filter((m) => m.id !== t.requester_id);
                              if (scoped.length === 0) return null;
                              return (
                                <optgroup key={dept} label={dept}>
                                  {scoped.map((m) => <option key={m.id} value={m.id}>{m.username}</option>)}
                                </optgroup>
                              );
                            })}
                          </>
                        )}
                      </select>
                      <button onClick={() => void dispatchTicket(t)} disabled={!draft[t.id]}
                        className="rounded-md bg-slate-800 text-white px-3 py-1.5 text-xs font-medium disabled:opacity-40 hover:bg-slate-700">派发</button>
                    </div>
                  </div>
                );
              })}
              {activeTickets.length === 0 && (
                <p className="py-8 text-center text-sm text-slate-400">当前没有待处理的工单</p>
              )}
            </div>
          </section>

          <section className="bg-white border border-slate-200 rounded-xl p-5">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-slate-900">待办事项</h3>
              <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs text-slate-500">未完成 {openTodos.length} 条</span>
            </div>
            <div className="space-y-2">
              {openTodos.map((todo) => (
                <div key={todo.id} className="rounded-lg border border-slate-200 p-3 flex items-center justify-between gap-3 hover:border-indigo-200 transition">
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-slate-800 truncate">{todo.title}</div>
                    <div className="text-xs text-slate-500 mt-0.5 flex items-center gap-1.5">
                      负责人 {todo.assignee_name} ·
                      <span className={`inline-flex items-center gap-1 ${todo.status === "pending" ? "text-amber-600" : "text-blue-600"}`}>
                        <span className={`h-1.5 w-1.5 rounded-full ${todo.status === "pending" ? "bg-amber-500" : "bg-blue-500"}`} />
                        {todo.status === "pending" ? "待处理" : "处理中"}
                      </span>
                    </div>
                  </div>
                  <div className="flex shrink-0 gap-1.5">
                    {todo.status === "pending" && (
                      <button onClick={() => void setTodoStatus(todo.id, "in_progress")} className="rounded-md border border-slate-300 px-2.5 py-1 text-xs text-slate-600 hover:bg-slate-50">开始</button>
                    )}
                    <button onClick={() => void setTodoStatus(todo.id, "completed")} className="rounded-md bg-emerald-600 text-white px-2.5 py-1 text-xs font-medium hover:bg-emerald-500">完成</button>
                    <button onClick={() => void setTodoStatus(todo.id, "cancelled")} className="rounded-md border border-slate-300 px-2.5 py-1 text-xs text-slate-500 hover:bg-slate-50">取消</button>
                  </div>
                </div>
              ))}
              {openTodos.length === 0 && <p className="py-6 text-center text-sm text-slate-400">没有未完成的待办</p>}
            </div>
          </section>
        </div>

        {/* 右列：分发入口 + 历史记录 */}
        <aside className="space-y-5">
          <section className="bg-white border border-slate-200 rounded-xl p-5">
            <h3 className="font-semibold text-slate-900 mb-4">直接分发待办</h3>
            <form onSubmit={dispatch} className="space-y-2.5">
              <select value={assignee} onChange={(e) => setAssignee(e.target.value)} className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500">
                <option value="">选择员工</option>
                {users.filter((u) => u.role === "employee").map((u) => <option key={u.id} value={u.id}>{u.username}</option>)}
              </select>
              <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="待办标题" className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
              <textarea value={description} onChange={(e) => setDescription(e.target.value)} placeholder="说明" rows={3} className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500" />
              <button className="w-full rounded-md bg-indigo-600 text-white py-2 text-sm font-medium hover:bg-indigo-500">分发待办</button>
            </form>
          </section>

          <section className="bg-white border border-slate-200 rounded-xl p-5">
            <h3 className="font-semibold text-slate-900 mb-4">历史记录</h3>
            <div className="space-y-1.5 max-h-96 overflow-y-auto">
              {doneTodos.map((todo) => (
                <div key={todo.id} className="rounded-lg border border-slate-100 p-2.5 flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <div className="text-xs font-medium text-slate-700 truncate">{todo.title}</div>
                    <div className="text-[11px] text-slate-400">负责人 {todo.assignee_name}</div>
                  </div>
                  <span className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] ${todo.status === "completed" ? "bg-emerald-50 text-emerald-600" : "bg-slate-100 text-slate-400"}`}>
                    {todo.status === "completed" ? "已完成" : "已取消"}
                  </span>
                </div>
              ))}
              {finishedTickets.map((t) => (
                <div key={t.id} className="rounded-lg border border-slate-100 p-2.5">
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-xs font-medium text-slate-700 truncate">{t.subject}</div>
                    <span className="shrink-0 text-[11px] text-slate-400">{statuses[t.status] ?? t.status}</span>
                  </div>
                  <div className="text-[11px] text-slate-400 mt-0.5">发起人 {t.requester_name} · 处理人 {t.target_user_name || "未派发"}</div>
                </div>
              ))}
              {doneTodos.length === 0 && finishedTickets.length === 0 && (
                <p className="py-6 text-center text-sm text-slate-400">暂无历史记录</p>
              )}
            </div>
          </section>
        </aside>
      </div>

      {/* 操作记录：底部全宽 */}
      <section className="bg-white border border-slate-200 rounded-xl p-5 mt-5">
        <h3 className="font-semibold text-slate-900 mb-4">操作记录</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-slate-400 border-b border-slate-200">
                <th className="py-2 font-medium">时间</th><th className="font-medium">操作人</th><th className="font-medium">动作</th><th className="font-medium">说明</th>
              </tr>
            </thead>
            <tbody>
              {events.map((event) => (
                <tr key={event.id} className="border-b border-slate-100">
                  <td className="py-2 text-xs text-slate-500 whitespace-nowrap">{new Date(event.created_at).toLocaleString()}</td>
                  <td className="text-xs text-slate-700">{event.actor_name}</td>
                  <td className="text-xs">
                    <span className="rounded bg-slate-100 px-1.5 py-0.5 text-slate-600">{eventTypeLabels[event.event_type] ?? event.event_type}</span>
                  </td>
                  <td className="text-xs text-slate-600">{event.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {events.length === 0 && <p className="text-sm text-slate-400 py-4 text-center">暂无操作记录</p>}
        </div>
      </section>

      {/* 沟通记录弹窗：点「沟通记录」弹出，管理员可在其中直接回复双方 */}
      {selected && (
        <div className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-black/30 p-6" onClick={closeConversation}>
          <div className="my-auto w-full max-w-2xl rounded-xl bg-white shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-start justify-between gap-4 border-b border-slate-200 p-5">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="font-semibold text-slate-900 truncate">{selected.subject}</h3>
                  <StatusPill status={selected.status} />
                  <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-500">{labels[selected.ticket_type]}</span>
                </div>
                <p className="text-xs text-slate-500 mt-1">
                  {selected.requester_name} ↔ {selected.target_user_name || "未派发"} · 双方全部交流如下
                </p>
              </div>
              <button onClick={closeConversation} className="shrink-0 rounded-md px-2 py-1 text-sm text-slate-400 hover:bg-slate-100 hover:text-slate-600">✕</button>
            </div>

            <div className="space-y-3 max-h-[50vh] overflow-y-auto p-5">
              {messages.map((m) => {
                const mine = m.sender_id === userId;
                return (
                  <div key={m.id} className={`flex ${mine ? "justify-end" : "justify-start"}`}>
                    <div className={`max-w-[80%] rounded-lg px-3.5 py-2 text-sm ${mine ? "bg-indigo-600 text-white" : "bg-slate-100 text-slate-800"}`}>
                      <div className={`text-[11px] mb-0.5 ${mine ? "text-indigo-200" : "text-slate-400"}`}>
                        {mine ? "我（管理员）" : m.sender_name} · {new Date(m.created_at).toLocaleString()}
                      </div>
                      <p className="whitespace-pre-wrap">{m.content}</p>
                    </div>
                  </div>
                );
              })}
              {messages.length === 0 && <p className="py-8 text-center text-sm text-slate-400">暂无沟通记录</p>}
            </div>

            <div className="border-t border-slate-200 p-4">
              {FINISHED.has(selected.status) ? (
                <p className="text-sm text-slate-400 text-center py-1">工单{statuses[selected.status] ?? selected.status}，沟通已关闭</p>
              ) : (
                <form onSubmit={sendReply} className="flex gap-2">
                  <input
                    value={reply}
                    onChange={(e) => setReply(e.target.value)}
                    placeholder="以管理员身份回复，双方可见…"
                    className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                  <button disabled={sending || !reply.trim()} className="rounded-md bg-indigo-600 text-white px-4 py-2 text-sm font-medium hover:bg-indigo-500 disabled:opacity-40">
                    {sending ? "发送中..." : "发送"}
                  </button>
                </form>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
