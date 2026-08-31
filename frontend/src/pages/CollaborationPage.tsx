import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "../store/auth";
import EmployeeHeader from "../components/EmployeeHeader";
import { usePolling } from "../hooks/usePolling";
import {
  addTicketMessage, createTicket, listDepartments, listNotifications, listParticipants, listTicketMessages,
  listTickets, listTodos, markAllNotificationsRead, markNotificationRead, ticketAction, updateTodo,
} from "../api/tickets";
import type { Department, Notification, Ticket, TicketMessage, TicketType, Todo, UserOption } from "../types";
import { notificationTarget } from "../phase1Navigation";
import { NOTIFICATIONS_CLEARED_EVENT, notifyNotificationsCleared } from "../notificationEvents";

const labels: Record<TicketType, string> = { same_department: "同部门协助", cross_department: "跨部门协助", question: "业务询问", issue: "问题反馈" };
const statusLabels: Record<string, string> = { pending_acceptance: "待接收", pending_admin: "待管理员审批", in_progress: "处理中", answered: "已回复", completed: "已完成", rejected: "已拒绝", closed: "已关闭", cancelled: "已撤回" };
const FINISHED = new Set(["completed", "closed", "cancelled", "rejected"]);

export default function CollaborationPage() {
  const navigate = useNavigate();
  const { departments, userId } = useAuthStore();
  const me = userId ?? "";
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [todos, setTodos] = useState<Todo[]>([]);
  const [participants, setParticipants] = useState<UserOption[]>([]);
  const [allDepartments, setAllDepartments] = useState<Department[]>([]);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [selected, setSelected] = useState<Ticket | null>(null);
  const [messages, setMessages] = useState<TicketMessage[]>([]);
  const [reply, setReply] = useState("");
  const [type, setType] = useState<TicketType>("same_department");
  const [subject, setSubject] = useState("");
  const [description, setDescription] = useState("");
  const [target, setTarget] = useState("");
  const [requestedDept, setRequestedDept] = useState("");
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState("");
  const [tab, setTab] = useState<"received" | "sent" | "todos">("received");
  const [bellOpen, setBellOpen] = useState(false);
  const [toast, setToast] = useState<Notification | null>(null);
  const [clearingNotifications, setClearingNotifications] = useState(false);

  useEffect(() => { setTarget(""); setRequestedDept(""); }, [type]);

  // 用 ref 保存最新选中项，避免轮询闭包拿到旧的 selected
  const selectedRef = useRef<Ticket | null>(null);
  useEffect(() => { selectedRef.current = selected; }, [selected]);
  const prevUnread = useRef(0);

  async function refresh() {
    try {
      const [t, d, n] = await Promise.all([listTickets(), listTodos(), listNotifications()]);
      setTickets(t); setTodos(d); setNotifications(n);
      const cur = selectedRef.current;
      if (cur) {
        const updated = t.find((x) => x.id === cur.id) ?? null;
        selectedRef.current = updated;
        setSelected(updated);
        // 实时刷新选中工单的回复，无需手动刷新页面
        try { setMessages(await listTicketMessages(cur.id)); } catch { setMessages([]); }
      }
      const unreadNow = n.filter((x) => !x.read_at).length;
      if (unreadNow > prevUnread.current) {
        const latest = n.find((x) => !x.read_at);
        if (latest) setToast(latest);
      }
      prevUnread.current = unreadNow;
    } catch {
      // 单次拉取失败保留上一次数据，下一轮自动重试，不清空页面。
    }
  }

  // 固定后台轮询，页面不再展示手动刷新控件。
  usePolling(() => refresh(), { interval: 10_000, paused: saving });

  useEffect(() => {
    void refresh();
    listParticipants().then(setParticipants).catch(() => {});
    listDepartments().then(setAllDepartments).catch(() => {});
    // Initial route hydration only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const clearLocalNotifications = () => {
      setNotifications((current) => current.map((item) => ({ ...item, read_at: item.read_at ?? new Date().toISOString() })));
      setToast(null);
      prevUnread.current = 0;
    };
    window.addEventListener(NOTIFICATIONS_CLEARED_EVENT, clearLocalNotifications);
    return () => window.removeEventListener(NOTIFICATIONS_CLEARED_EVENT, clearLocalNotifications);
  }, []);

  const unread = useMemo(() => notifications.filter((n) => !n.read_at).length, [notifications]);
  const pending = useMemo(() => todos.filter((t) => t.status !== "completed" && t.status !== "cancelled").length, [todos]);
  const received = useMemo(() => tickets.filter((t) => t.requester_id !== me), [tickets, me]);
  const sent = useMemo(() => tickets.filter((t) => t.requester_id === me), [tickets, me]);

  const myDepartmentIds = useMemo(() => new Set(departments.map((d) => d.id)), [departments]);
  const sameDepartmentParticipants = useMemo(
    () => participants.filter((p) => p.departments?.some((id) => myDepartmentIds.has(id))),
    [participants, myDepartmentIds]
  );
  const crossDepartments = useMemo(
    () => allDepartments.filter((d) => !departments.some((m) => m.id === d.id)),
    [allDepartments, departments]
  );

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!subject.trim() || !description.trim()) return;
    if (type === "cross_department" && !requestedDept) { setNotice("请选择需要协助的部门"); return; }
    if (type === "same_department" && !target) { setNotice("请选择同部门的处理人"); return; }
    setSaving(true);
    try {
      await createTicket({
        ticket_type: type,
        subject,
        description,
        target_user_id: type === "cross_department" ? undefined : (target || undefined),
        department_id: departments[0]?.id,
        requested_department_id: type === "cross_department" ? requestedDept : undefined,
      });
      setSubject(""); setDescription(""); setTarget(""); setRequestedDept(""); setNotice("工单已提交");
      await refresh();
    } catch {
      setNotice("提交失败，请检查工单类型和处理人");
    } finally {
      setSaving(false);
    }
  }
  async function act(action: string) {
    if (!selected) return;
    try {
      const updated = await ticketAction(selected.id, action);
      setSelected(updated);
      await refresh();
    } catch {
      setNotice(action === "reopen" ? "只有工单发起人可以在关闭后 3 天内重新打开" : "工单操作失败，请稍后重试");
    }
  }
  async function sendReply(e: React.FormEvent) {
    e.preventDefault();
    if (!selected || !reply.trim()) return;
    await addTicketMessage(selected.id, reply);
    setReply("");
    setMessages(await listTicketMessages(selected.id));
    await refresh();
  }
  async function completeTodo(id: string) { await updateTodo(id, "completed"); await refresh(); }
  async function clearNotifications() {
    if (clearingNotifications || unread === 0) return;
    setClearingNotifications(true);
    try {
      await markAllNotificationsRead();
      setNotifications((current) => current.map((item) => ({ ...item, read_at: item.read_at ?? new Date().toISOString() })));
      setToast(null);
      prevUnread.current = 0;
      notifyNotificationsCleared();
    } catch {
      setNotice("通知清空失败，请稍后重试");
    } finally {
      setClearingNotifications(false);
    }
  }
  async function openNotification(n: Notification) {
    if (!n.read_at) { await markNotificationRead(n.id).catch(() => {}); setNotifications((prev) => prev.map((x) => x.id === n.id ? { ...x, read_at: new Date().toISOString() } : x)); }
    setToast(null); setBellOpen(false);
    const target = notificationTarget(n);
    if (target) {
      navigate(target);
      return;
    }
    if (n.ticket_id) {
      const t = tickets.find((x) => x.id === n.ticket_id);
      if (t) { setTab("received"); setSelected(t); }
    }
  }

  const listForTab = tab === "sent" ? sent : tab === "todos" ? [] : received;

  return (
    <div className="min-h-screen bg-slate-50">
      <EmployeeHeader />
      <div className="p-6">
      <div className="max-w-6xl mx-auto">
        <div className="flex items-center justify-between mb-5">
          <div>
            <h1 className="text-xl font-semibold text-slate-900">协作中心</h1>
            <p className="text-sm text-slate-500 mt-1">工单、协助和待办统一处理</p>
          </div>
          <div className="flex flex-wrap items-center justify-end gap-4">
            <div className="relative">
              <button onClick={() => setBellOpen((v) => !v)} className="relative rounded-full p-2 text-slate-500 hover:bg-slate-100" title="消息通知">
                <span className="text-lg">🔔</span>
                {unread > 0 && <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 px-1 rounded-full bg-red-500 text-white text-[10px] leading-4 text-center">{unread}</span>}
              </button>
              {bellOpen && (
                <div className="absolute right-0 mt-2 w-80 max-h-96 overflow-y-auto bg-white border border-slate-200 rounded-lg shadow-lg z-20">
                  <div className="flex items-center justify-between border-b border-slate-200 px-3 py-2 text-sm font-medium"><span>消息通知{unread > 0 ? `（${unread} 条未读）` : ""}</span><button onClick={() => void clearNotifications()} disabled={clearingNotifications || unread === 0} className="text-xs font-normal text-slate-500 hover:text-indigo-600 disabled:cursor-not-allowed disabled:opacity-40">{clearingNotifications ? "清空中..." : "清空通知"}</button></div>
                  {notifications.length === 0 && <p className="text-sm text-slate-400 px-3 py-4">暂无消息</p>}
                  {notifications.map((n) => (
                    <button key={n.id} onClick={() => void openNotification(n)} className={`w-full text-left px-3 py-2 border-b border-slate-100 text-sm hover:bg-slate-50 ${n.read_at ? "text-slate-400" : "text-slate-800"}`}>
                      <div className="truncate">{n.content}</div>
                      <div className="text-[11px] text-slate-400 mt-0.5">{new Date(n.created_at).toLocaleString()}</div>
                    </button>
                  ))}
                </div>
              )}
            </div>
            <span className="text-sm text-slate-500">待办 {pending} 项 · 未读 {unread}</span>
          </div>
        </div>

        {toast && (
          <div className="mb-4 flex items-center justify-between gap-4 rounded-lg border border-indigo-200 bg-indigo-50 px-4 py-3">
            <button onClick={() => void openNotification(toast)} className="text-sm text-indigo-700 text-left flex-1">🔔 {toast.content}</button>
            <button onClick={() => setToast(null)} className="text-xs text-slate-400 hover:text-slate-600">关闭</button>
          </div>
        )}

        <div className="grid lg:grid-cols-[360px_1fr] gap-5">
          <section className="bg-white border border-slate-200 rounded-lg p-4">
            <h2 className="font-medium mb-3">发起工单</h2>
            <form onSubmit={submit} className="space-y-3">
              <select value={type} onChange={(e) => setType(e.target.value as TicketType)} className="w-full rounded border border-slate-300 px-3 py-2 text-sm">
                {Object.entries(labels).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
              {type === "cross_department" ? (
                <>
                  <select value={requestedDept} onChange={(e) => setRequestedDept(e.target.value)} className="w-full rounded border border-slate-300 px-3 py-2 text-sm">
                    <option value="">选择需要协助的部门</option>
                    {crossDepartments.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                  </select>
                  <p className="text-xs text-slate-400">提交后上报管理员，由管理员调度给该部门的同事</p>
                </>
              ) : (
                <select value={target} onChange={(e) => setTarget(e.target.value)} className="w-full rounded border border-slate-300 px-3 py-2 text-sm">
                  <option value="">选择处理人</option>
                  {type === "same_department" ? (
                    sameDepartmentParticipants.map((p) => <option key={p.id} value={p.id}>{p.username}</option>)
                  ) : (
                    <>
                      <option value="admin">管理员</option>
                      {participants.map((p) => <option key={p.id} value={p.id}>{p.username}</option>)}
                    </>
                  )}
                </select>
              )}
              <input value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="主题" className="w-full rounded border border-slate-300 px-3 py-2 text-sm" />
              <textarea value={description} onChange={(e) => setDescription(e.target.value)} placeholder="详细描述" rows={5} className="w-full rounded border border-slate-300 px-3 py-2 text-sm" />
              <button disabled={saving} className="w-full rounded bg-indigo-600 text-white py-2 text-sm disabled:opacity-50">{saving ? "提交中..." : "提交工单"}</button>
            </form>
            {notice && <p className="text-sm text-slate-500 mt-3">{notice}</p>}
          </section>

          <section className="bg-white border border-slate-200 rounded-lg p-4">
            <div className="flex gap-4 border-b border-slate-200 mb-3">
              <button onClick={() => setTab("received")} className={`font-medium pb-2 ${tab === "received" ? "border-b-2 border-indigo-600" : "text-slate-500 border-b-2 border-transparent"}`}>我收到的工单</button>
              <button onClick={() => setTab("sent")} className={`font-medium pb-2 ${tab === "sent" ? "border-b-2 border-indigo-600" : "text-slate-500 border-b-2 border-transparent"}`}>我发出的请求 ({sent.length})</button>
              <button onClick={() => setTab("todos")} className={`font-medium pb-2 ${tab === "todos" ? "border-b-2 border-indigo-600" : "text-slate-500 border-b-2 border-transparent"}`}>我的待办 ({pending})</button>
            </div>

            {tab === "todos" ? (
              <div className="space-y-2 max-h-[560px] overflow-y-auto">
                {todos.map((t) => (
                  <div key={t.id} className="flex items-center justify-between p-3 rounded border border-slate-200">
                    <div className="min-w-0">
                      <div className="text-sm font-medium truncate">{t.title}</div>
                      <div className="text-xs text-slate-500 mt-1">来自 {t.creator_name} · {statusLabels[t.status] ?? t.status}</div>
                    </div>
                    {t.status !== "completed" && t.status !== "cancelled" && (
                      <button onClick={() => void completeTodo(t.id)} className="text-xs bg-emerald-600 text-white px-3 py-1.5 rounded">完成</button>
                    )}
                  </div>
                ))}
                {todos.length === 0 && <p className="text-sm text-slate-400">暂无待办</p>}
              </div>
            ) : (
              <div className="grid md:grid-cols-[280px_1fr] gap-4">
                <div className="space-y-2 max-h-[560px] overflow-y-auto">
                  {listForTab.map((t) => (
                    <button key={t.id} onClick={() => setSelected(t)} className={`w-full text-left p-3 rounded border ${selected?.id === t.id ? "border-indigo-300 bg-indigo-50" : "border-slate-200"}`}>
                      <div className="text-sm font-medium truncate">{t.subject}</div>
                      <div className="text-xs text-slate-500 mt-1">{labels[t.ticket_type]} · {statusLabels[t.status] ?? t.status}</div>
                      {tab === "sent" && <div className="text-[11px] text-slate-400 mt-1">处理人：{t.target_user_name || "—"}</div>}
                    </button>
                  ))}
                  {listForTab.length === 0 && <p className="text-sm text-slate-400">{tab === "sent" ? "你还没有发出任何请求" : "暂无收到的工单"}</p>}
                </div>
                <div>
                  {selected ? (
                    <>
                      <div className="border-b border-slate-200 pb-3">
                        <h3 className="font-medium">{selected.subject}</h3>
                        <p className="text-sm text-slate-600 whitespace-pre-wrap mt-2">{selected.description}</p>
                        <div className="flex gap-2 mt-3">
                          {/* 只有处理人（非发起者）才能接受/拒绝 */}
                          {selected.status === "pending_acceptance" && selected.requester_id !== me && (
                            <>
                              <button onClick={() => void act("accept")} className="text-xs bg-emerald-600 text-white px-3 py-1.5 rounded">接受</button>
                              <button onClick={() => void act("reject")} className="text-xs bg-slate-200 px-3 py-1.5 rounded">拒绝</button>
                            </>
                          )}
                          {selected.status === "in_progress" && <button onClick={() => void act("complete")} className="text-xs bg-indigo-600 text-white px-3 py-1.5 rounded">已完成</button>}
                          {(selected.status === "closed" || selected.status === "completed") && selected.requester_id === me && selected.closed_at && <button onClick={() => void act("reopen")} className="text-xs bg-indigo-600 text-white px-3 py-1.5 rounded">重新打开</button>}
                          {selected.requester_id === me && <span className="text-xs text-slate-400 self-center">（这是我发出的请求）</span>}
                        </div>
                      </div>
                      <div className="py-3 space-y-2 max-h-64 overflow-y-auto">
                        {messages.map((m) => <div key={m.id} className="text-sm"><span className="font-medium">{m.sender_name}：</span>{m.content}</div>)}
                        {messages.length === 0 && <p className="text-sm text-slate-400">暂无回复</p>}
                      </div>
                      {FINISHED.has(selected.status) ? (
                        <p className="text-sm text-slate-400 py-2">工单{statusLabels[selected.status] ?? selected.status}，沟通已关闭</p>
                      ) : (
                        <form onSubmit={sendReply} className="flex gap-2">
                          <input value={reply} onChange={(e) => setReply(e.target.value)} placeholder="输入回复…" className="flex-1 rounded border border-slate-300 px-3 py-2 text-sm" />
                          <button className="rounded bg-indigo-600 text-white px-4 py-2 text-sm">发送</button>
                        </form>
                      )}
                    </>
                  ) : <p className="text-sm text-slate-400">请选择左侧工单查看详情</p>}
                </div>
              </div>
            )}
          </section>
        </div>
      </div>
      </div>
    </div>
  );
}
