import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useAuthStore } from "../store/auth";
import { listNotifications, markAllNotificationsRead } from "../api/tickets";
import { usePolling } from "../hooks/usePolling";
import AccountSwitcher from "./AccountSwitcher";
import BackButton from "./BackButton";
import { notifyNotificationsCleared } from "../notificationEvents";

const navItems = [
  { to: "/chat", label: "知识助手" },
  { to: "/collaboration", label: "协作中心" },
  { to: "/expenses", label: "费用报销" },
];

interface Props {
  fallback?: string;
  extra?: React.ReactNode;
}

export default function EmployeeHeader({ fallback = "/chat", extra }: Props) {
  const location = useLocation();
  const { logout, role } = useAuthStore();
  // 未读协作消息数：轮询通知接口，在「协作中心」入口上挂红点徽标，
  // 员工停在问答界面也能第一时间知道有新请求需要处理。
  const [unread, setUnread] = useState(0);
  const [clearing, setClearing] = useState(false);

  async function refreshUnread() {
    try {
      const notes = await listNotifications();
      setUnread(notes.filter((n) => !n.read_at).length);
    } catch {
      // 拉取失败保持上一次数量，下一轮自动重试。
    }
  }

  async function clearAll() {
    if (clearing || unread === 0) return;
    setClearing(true);
    try {
      await markAllNotificationsRead();
      setUnread(0);
      notifyNotificationsCleared();
    } catch {
      // 失败后保持原数量
    } finally {
      setClearing(false);
    }
  }

  usePolling(refreshUnread, { interval: 10_000, enabled: role !== "admin" });
  useEffect(() => { void refreshUnread(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <header className="border-b border-slate-200 bg-white px-6 py-3 flex items-center justify-between">
      <div className="flex items-center gap-4">
        <BackButton fallback={fallback} />
        <span className="font-semibold text-slate-900">企业智能检索系统</span>
        <nav className="flex items-center gap-1">
          {navItems.map((item) => {
            const selected = location.pathname === item.to;
            const isCollaboration = item.to === "/collaboration";
            return (
              <Link
                key={item.to}
                to={item.to}
                className={`relative rounded-md px-3 py-1.5 text-sm transition ${
                  selected
                    ? "bg-indigo-50 text-indigo-700 font-medium"
                    : "text-slate-500 hover:bg-slate-50 hover:text-slate-700"
                }`}
              >
                {item.label}
                {isCollaboration && unread > 0 && (
                  <span className="absolute -top-1 -right-1 inline-flex min-w-[16px] h-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-semibold leading-none text-white">
                    {unread > 99 ? "99+" : unread}
                  </span>
                )}
              </Link>
            );
          })}
        </nav>
        {extra}
      </div>
      <div className="flex items-center gap-2">
        {role !== "admin" && (
          <button
            onClick={() => void clearAll()}
            disabled={clearing || unread === 0}
            title="一键清空通知"
            className="rounded-md px-2 py-1 text-xs text-slate-500 hover:bg-slate-100 hover:text-slate-700 disabled:opacity-50"
          >
            {clearing ? "清空中..." : "清空通知"}
          </button>
        )}
        <AccountSwitcher />
        <Link
          to="/login"
          onClick={() => logout()}
          className="text-sm text-slate-400 hover:text-slate-700"
        >
          退出登录
        </Link>
      </div>
    </header>
  );
}
