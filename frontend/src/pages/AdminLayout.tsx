import { useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuthStore } from "../store/auth";
import BackButton from "../components/BackButton";
import AccountSwitcher from "../components/AccountSwitcher";
import { usePolling } from "../hooks/usePolling";
import { listNotifications, listTodos, markAllNotificationsRead, markNotificationRead } from "../api/tickets";
import type { Notification } from "../types";

interface NavItem {
  to: string;
  label: string;
  /** 重要消息数量徽标：>0 时在该导航项上高亮提示。 */
  badge?: number;
  end?: boolean;
}

interface NavGroup {
  label: string;
  items: NavItem[];
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

  const groups: NavGroup[] = [
    {
      label: "工作台",
      items: [{ to: "/admin/dashboard", label: "管理驾驶舱" }],
    },
    {
      label: "组织人事",
      items: [
        { to: "/admin", label: "部门管理", end: true },
        { to: "/admin/organization", label: "组织与员工" },
        { to: "/admin/work-schedules", label: "排班管理" },
        { to: "/admin/payroll", label: "薪酬与发薪" },
      ],
    },
    {
      label: "协作工单",
      items: [{ to: "/admin/tickets", label: "工单与待办", badge: counts.todos }],
    },
    { label: "财务管理", items: [{ to: "/admin/expenses", label: "费用报销" }] },
    {
      label: "数据监控",
      items: [{ to: "/admin/sensitive-events", label: "敏感记录" }],
    },
    {
      label: "经营资产",
      items: [
        { to: "/admin/projects", label: "项目工作台" },
        { to: "/admin/contracts", label: "合同台账" },
        { to: "/admin/knowledge", label: "知识文档" },
      ],
    },
  ];

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="sticky top-0 z-20 border-b border-slate-200 bg-white">
        <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3 px-6 py-3">
          <div className="flex items-center gap-5">
            <BackButton fallback="/admin" />
            <span className="whitespace-nowrap font-semibold text-slate-900">
              企业智能检索系统 · 管理后台
            </span>
            <nav className="flex flex-wrap items-end gap-x-6 gap-y-2">
              {groups.map((group) => (
                <div key={group.label} className="flex flex-col gap-1">
                  <span className="text-[10px] font-medium uppercase tracking-wider text-slate-400">
                    {group.label}
                  </span>
                  <div className="flex items-center gap-3">
                    {group.items.map((item) => (
                      <NavLinkItem key={item.to} item={item} />
                    ))}
                  </div>
                </div>
              ))}
            </nav>
          </div>

          <div className="flex items-center gap-3">
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
