import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchMe, login as apiLogin } from "../api/auth";
import { isAccountFresh, useAuthStore, type SavedAccount } from "../store/auth";
import { formatAccountRoleLabel } from "../accountFormat";
import type { Role } from "../types";

function homeFor(role: Role): string {
  return role === "admin" ? "/admin" : "/chat";
}

export interface AccountSwitcherProps {
  /** 附加到账号菜单里的自定义项（例如「我的记忆」）。 */
  extraItems?: { label: string; onClick: () => void }[];
}

export default function AccountSwitcher({ extraItems = [] }: AccountSwitcherProps = {}) {
  const { accounts, userId, username, role, roles, switchTo, removeAccount } = useAuthStore();
  const [open, setOpen] = useState(false);
  // 令牌已过期的账号：切换时需要重新输入密码
  const [pending, setPending] = useState<SavedAccount | null>(null);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  function startSwitch(acc: SavedAccount) {
    if (acc.userId === userId) { setOpen(false); return; }
    if (isAccountFresh(acc)) {
      // 令牌还在有效期内，先静默校验一次，失败则回退到输密码
      setBusy(true);
      fetchMe(acc.token)
        .then(() => {
          const prevRole = role;
          switchTo(acc.userId);
          setOpen(false);
          // 跨角色切换时跳到对应默认页（避免被 ProtectedRoute 踢回登录）；
          // 同角色切换则留在当前页，由 App 里的 key={userId} 触发重挂载刷新数据。
          if (acc.role !== prevRole) navigate(homeFor(acc.role));
        })
        .catch(() => { setPending(acc); setPassword(""); setError(""); })
        .finally(() => setBusy(false));
      return;
    }
    setPending(acc); setPassword(""); setError("");
  }

  async function submitPassword(e: React.FormEvent) {
    e.preventDefault();
    if (!pending || !password) return;
    setBusy(true); setError("");
    try {
      const res = await apiLogin(pending.username, password);
      // login 会用新令牌覆盖该账号并切为当前会话
      const prevRole = role;
      useAuthStore.getState().login(res.access_token, res.user_id, res.username, res.role, res.department_id, res.departments, res.roles);
      setPending(null); setPassword(""); setOpen(false);
      if (res.role !== prevRole) navigate(homeFor(res.role));
    } catch {
      setError("密码错误，请重试");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="relative" ref={boxRef}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1 rounded border border-slate-200 px-2.5 py-1 text-sm text-slate-600 hover:bg-slate-50"
        title="切换账号"
      >
        <span className="w-5 h-5 rounded-full bg-indigo-100 text-indigo-700 text-[11px] leading-5 text-center">
          {(username ?? "?").slice(0, 1).toUpperCase()}
        </span>
        <span>{username}</span>
        <span className="text-slate-400">{formatAccountRoleLabel(role ?? "employee", roles)}</span>
        <span className="text-slate-400 text-xs">▾</span>
      </button>

      {open && !pending && (
        <div className="absolute right-0 mt-1 w-64 bg-white border border-slate-200 rounded-lg shadow-lg z-50 py-1">
          <div className="px-3 py-1.5 text-xs text-slate-400">已记住的账号</div>
          {accounts.map((acc) => {
            const fresh = isAccountFresh(acc);
            const current = acc.userId === userId;
            return (
              <div key={acc.userId} className="flex items-center gap-1 px-1">
                <button
                  onClick={() => startSwitch(acc)}
                  disabled={busy}
                  className="flex-1 text-left px-2 py-1.5 rounded hover:bg-slate-50 disabled:opacity-50"
                >
                  <div className="text-sm text-slate-700">
                    {acc.username}
                    {current && <span className="ml-1 text-[11px] text-indigo-600">当前</span>}
                  </div>
                  <div className="text-[11px] text-slate-400">
                    {formatAccountRoleLabel(acc.role, acc.roles ?? [])}
                    {!fresh && !current && <span className="ml-1 text-amber-600">需重新验证</span>}
                  </div>
                </button>
                <button
                  onClick={() => removeAccount(acc.userId)}
                  title="忘记此账号"
                  className="px-1.5 py-1 text-xs text-slate-300 hover:text-red-500"
                >
                  ✕
                </button>
              </div>
            );
          })}
          {accounts.length === 0 && <div className="px-3 py-2 text-xs text-slate-400">暂无记住的账号</div>}
          {extraItems.map((item) => (
            <button
              key={item.label}
              onClick={() => { setOpen(false); item.onClick(); }}
              className="w-full text-left px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50"
            >
              {item.label}
            </button>
          ))}
          <div className="border-t border-slate-100 mt-1 pt-1">
            <button
              onClick={() => { setOpen(false); navigate("/login"); }}
              className="w-full text-left px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50"
            >
              + 添加其他账号
            </button>
          </div>
        </div>
      )}

      {open && pending && (
        <div className="absolute right-0 mt-1 w-64 bg-white border border-slate-200 rounded-lg shadow-lg z-50 p-3">
          <div className="text-sm text-slate-700 mb-2">切换到 {pending.username}</div>
          <form onSubmit={submitPassword} className="space-y-2">
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="输入密码"
              autoFocus
              className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
            />
            {error && <p className="text-xs text-red-500">{error}</p>}
            <div className="flex gap-2">
              <button type="submit" disabled={busy || !password} className="flex-1 rounded bg-indigo-600 text-white py-1.5 text-sm disabled:opacity-50">
                {busy ? "验证中…" : "登录"}
              </button>
              <button type="button" onClick={() => setPending(null)} className="rounded border border-slate-300 px-3 py-1.5 text-sm text-slate-600">
                取消
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
