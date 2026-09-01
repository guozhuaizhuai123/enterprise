import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuthStore } from "../store/auth";
import BackButton from "../components/BackButton";
import AccountSwitcher from "../components/AccountSwitcher";
import { usePolling } from "../hooks/usePolling";
import { primaryAdminRoutes } from "../adminNavigation";
import { listNotifications, listTodos, markAllNotificationsRead, markNotificationRead } from "../api/tickets";
import type { Notification } from "../types";

interface NavItem {
  to: string;
  label: string;
  /** 重要消息数量徽标：>0 时在该导航项上高亮提示。 */
  badge?: number;
  end?: boolean;
}

function navClass(isActive: boolean): string {
  return `text-sm ${isActive ? "text-indigo-600 font-semibold" : "text-slate-600 hover:text-slate-900"}`;
}

function NavLinkItem({ item }: { item: NavItem }) {
  const hasBadge = (item.badge ?? 0) > 0;
  return (
    <NavLink
      to={item.to}
      end={item.end}
      className={({ isActive }) =>
        `relative inline-flex items-center gap-1.5 ${navClass(isActive)}`
      }
    >
      {item.label}
      {hasBadge && (
        <span className="inline-flex min-w-[18px] h-[18px] items-center justify-center rounded-full bg-rose-500 px-1 text-[11px] font-semibold leading-none text-white">
          {item.badge}
        </span>
      )}
    </NavLink>
  );
}

interface PendingCounts {
  todos: number;
  unread: number;
}

export default function AdminLayout() {
  const { logout } = useAuthStore();
  const navigate = useNavigate();
  const location = useLocation();
  const [counts, setCounts] = useState<PendingCounts>({ todos: 0, unread: 0 });
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [bellOpen, setBellOpen] = useState(false);
  const [clearing, setClearing] = useState(false);

  function handleLogout() {
    logout();
    navigate("/login");
  }

  const { refreshNow } = usePolling(
    async () => {
      const [todos, notes] = await Promise.all([
        listTodos(),
        listNotifications(),
      ]);
      const pendingTodos = todos.filter((t) => t.status !== "completed").length;
      const unread = notes.filter((n) => n.read_at === null).length;
      setCounts({ todos: pendingTodos, unread });
      setNotifications(notes);
    },
    { interval: 10_000 },
  );

  async function clearAllNotifications() {
    if (clearing || counts.unread === 0) return;
    setClearing(true);
    try {
      await markAllNotificationsRead();
      setNotifications((current) => current.map((item) => ({ ...item, read_at: item.read_at ?? new Date().toISOString() })));
      await refreshNow();
    } catch {
      // 失败时保持原数量
    } finally {
      setClearing(false);
    }
  }

  async function openNotification(notification: Notification) {
    if (!notification.read_at) {
      await markNotificationRead(notification.id).catch(() => {});
      setNotifications((current) => current.map((item) => item.id === notification.id ? { ...item, read_at: new Date().toISOString() } : item));
    }
    setBellOpen(false);
  }

  // 路由切换后立即刷新一次，确保进入页面时徽标是最新的
  useEffect(() => {
    void refreshNow();
  }, [location.pathname, refreshNow]);

  const primaryItems: NavItem[] = primaryAdminRoutes();

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="sticky top-0 z-20 border-b border-slate-200 bg-white">
        <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3 px-6 py-3">
          <div className="flex items-center gap-5">
            <BackButton fallback="/admin/assistant" />
            <span className="whitespace-nowrap font-semibold text-slate-900">
              企业智能检索系统 · 管理后台
            </span>
            {/* 一级导航只有管理助手与企业全景；其他页面通过助手导航、全景下钻
                或直接链接进入，路由全部保留。 */}
            <nav className="flex items-center gap-4">
              {primaryItems.map((item) => (
                <NavLinkItem key={item.to} item={item} />
              ))}
            </nav>
          </div>

          <div className="flex items-center gap-3">
            {counts.todos > 0 && (
              <NavLink
                to="/admin/tickets"
                className="inline-flex items-center gap-1.5 rounded-full bg-amber-50 px-2.5 py-1 text-xs text-amber-700 hover:bg-amber-100"
              >
                待办
                <span className="inline-flex min-w-[18px] items-center justify-center rounded-full bg-amber-500 px-1 text-[11px] font-semibold leading-none text-white">
                  {counts.todos > 99 ? "99+" : counts.todos}
                </span>
              </NavLink>
            )}
            <div className="relative">
              <button
                onClick={() => setBellOpen((open) => !open)}
                aria-label={counts.unread > 0 ? `消息通知 ${counts.unread}` : "消息通知"}
                title="消息通知"
                className="relative rounded-full p-2 text-slate-500 hover:bg-slate-100"
              >
                <span className="text-lg">🔔</span>
                {counts.unread > 0 && <span className="absolute -right-0.5 -top-0.5 inline-flex min-w-[16px] h-4 items-center justify-center rounded-full bg-rose-500 px-1 text-[10px] font-semibold leading-none text-white">{counts.unread > 99 ? "99+" : counts.unread}</span>}
              </button>
              {bellOpen && (
                <div className="absolute right-0 z-30 mt-2 max-h-96 w-80 overflow-y-auto rounded-lg border border-slate-200 bg-white shadow-lg">
                  <div className="flex items-center justify-between border-b border-slate-200 px-3 py-2 text-sm font-medium">
                    <span>消息通知{counts.unread > 0 ? `（${counts.unread} 条未读）` : ""}</span>
                    <button onClick={() => void clearAllNotifications()} disabled={clearing || counts.unread === 0} className="text-xs font-normal text-slate-500 hover:text-indigo-600 disabled:cursor-not-allowed disabled:opacity-40">{clearing ? "清空中..." : "清空通知"}</button>
                  </div>
                  {notifications.length === 0 && <p className="px-3 py-4 text-sm text-slate-400">暂无消息</p>}
                  {notifications.map((notification) => (
                    <button key={notification.id} onClick={() => void openNotification(notification)} className={`w-full border-b border-slate-100 px-3 py-2 text-left text-sm hover:bg-slate-50 ${notification.read_at ? "text-slate-400" : "text-slate-800"}`}>
                      <div className="truncate">{notification.content}</div>
                      <div className="mt-0.5 text-[11px] text-slate-400">{new Date(notification.created_at).toLocaleString()}</div>
                    </button>
                  ))}
                </div>
              )}
            </div>
            <AccountSwitcher />
            <button onClick={handleLogout} className="text-sm text-slate-400 hover:text-slate-700">
              退出登录
            </button>
          </div>
        </div>
      </header>
      <main className="p-6">
        <Outlet />
      </main>
    </div>
  );
}
