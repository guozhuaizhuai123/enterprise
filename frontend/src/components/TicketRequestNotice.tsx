import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { listNotifications, markNotificationRead } from "../api/tickets";
import { usePolling } from "../hooks/usePolling";
import { useAuthStore } from "../store/auth";
import type { Notification } from "../types";
import { NOTIFICATIONS_CLEARED_EVENT } from "../notificationEvents";

/** 与工单/协作相关的通知类型：有新请求或新回复时在问答界面给出醒目提示。 */
const TICKET_KINDS = new Set(["ticket_assigned", "ticket_replied", "todo_created"]);

const KIND_HINTS: Record<string, string> = {
  ticket_assigned: "新的协作请求",
  ticket_replied: "工单有新回复",
  todo_created: "新的待办任务",
};

/**
 * 问答界面顶部的协作请求提示条。
 * 轮询通知接口，只要有未读的工单类消息就展示，方便员工第一时间跳到协作中心处理。
 */
export default function TicketRequestNotice() {
  const navigate = useNavigate();
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [dismissed, setDismissed] = useState<string[]>([]);
  const { role } = useAuthStore();

  async function refresh() {
    try {
      setNotifications(await listNotifications());
    } catch {
      // 轮询失败保留上一次数据，下一轮自动重试。
    }
  }

  usePolling(refresh, { interval: 10_000 });
  useEffect(() => { void refresh(); }, []);

  useEffect(() => {
    const handleCleared = () => {
      setNotifications((current) => current.map((notification) => ({
        ...notification,
        read_at: notification.read_at ?? new Date().toISOString(),
      })));
      setDismissed([]);
    };
    window.addEventListener(NOTIFICATIONS_CLEARED_EVENT, handleCleared);
    return () => window.removeEventListener(NOTIFICATIONS_CLEARED_EVENT, handleCleared);
  }, []);

  const alerts = useMemo(
    () => notifications.filter((n) => !n.read_at && TICKET_KINDS.has(n.kind) && !dismissed.includes(n.id)),
    [notifications, dismissed],
  );

  if (role === "admin" || alerts.length === 0) return null;
  const latest = alerts[0];

  async function dismissOne(id: string) {
    setDismissed((prev) => [...prev, id]);
    await markNotificationRead(id).catch(() => {});
  }

  async function goHandle() {
    setDismissed((prev) => [...prev, latest.id]);
    await markNotificationRead(latest.id).catch(() => {});
    navigate("/collaboration");
  }

  return (
    <div className="flex items-center gap-3 border-b border-indigo-200 bg-indigo-50 px-6 py-2.5">
      <span className="shrink-0 rounded-full bg-indigo-600 px-2 py-0.5 text-[11px] font-medium text-white">
        {KIND_HINTS[latest.kind] ?? "协作消息"}
      </span>
      <button onClick={() => void goHandle()} className="min-w-0 flex-1 truncate text-left text-sm text-indigo-800 hover:underline">
        {latest.content}
        {alerts.length > 1 && <span className="ml-2 text-xs text-indigo-500">等 {alerts.length} 条协作消息</span>}
      </button>
      <button
        onClick={() => void goHandle()}
        className="shrink-0 rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-500"
      >
        去处理
      </button>
      <button
        onClick={() => void dismissOne(latest.id)}
        className="shrink-0 text-xs text-slate-400 hover:text-slate-600"
        title="稍后处理"
      >
        稍后
      </button>
    </div>
  );
}
