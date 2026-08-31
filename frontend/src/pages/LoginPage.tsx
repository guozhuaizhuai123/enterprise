import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { fetchMe, login } from "../api/auth";
import { isAccountFresh, useAuthStore, type SavedAccount } from "../store/auth";

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const doLogin = useAuthStore((s) => s.login);
  const accounts = useAuthStore((s) => s.accounts);
  const switchTo = useAuthStore((s) => s.switchTo);
  const removeAccount = useAuthStore((s) => s.removeAccount);

  /** 点击已记住的账号：令牌仍有效就直接进入，否则回填用户名等输入密码。 */
  async function quickSwitch(acc: SavedAccount) {
    setError("");
    if (isAccountFresh(acc)) {
      setLoading(true);
      try {
        await fetchMe(acc.token);
        switchTo(acc.userId);
        navigate(acc.role === "admin" ? "/admin" : "/chat");
      } catch {
        setUsername(acc.username);
        setError("该账号登录已过期，请输入密码重新登录");
      } finally {
        setLoading(false);
      }
      return;
    }
    setUsername(acc.username);
    setError("请输入密码以继续");
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await login(username, password);
      doLogin(res.access_token, res.user_id, res.username, res.role, res.department_id, res.departments, res.roles);
      navigate(res.role === "admin" ? "/admin" : "/chat");
    } catch (error) {
      const responseStatus = (error as { response?: { status?: number } }).response?.status;
      setError(
        responseStatus === 401
          ? "用户名或密码错误"
          : "后台服务未启动或暂不可用，请先启动后台服务",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50">
      <div className="w-full max-w-sm bg-white rounded-xl shadow-sm border border-slate-200 p-8">
        <h1 className="text-xl font-semibold text-slate-900 mb-1">企业智能检索系统</h1>
        <p className="text-sm text-slate-500 mb-6">登录以继续</p>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm text-slate-600 mb-1">用户名</label>
            <input
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoFocus
              required
            />
          </div>
          <div>
            <label className="block text-sm text-slate-600 mb-1">密码</label>
            <input
              type="password"
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
          {error && <p className="text-sm text-red-500">{error}</p>}
          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-md bg-indigo-600 text-white py-2 text-sm font-medium hover:bg-indigo-500 disabled:opacity-60"
          >
            {loading ? "登录中..." : "登录"}
          </button>
        </form>

        {accounts.length > 0 && (
          <div className="mt-6 border-t border-slate-200 pt-4">
            <p className="text-xs text-slate-400 mb-2">已记住的账号，点击直接切换</p>
            <div className="space-y-1">
              {accounts.map((acc) => {
                const fresh = isAccountFresh(acc);
                return (
                  <div key={acc.userId} className="flex items-center gap-1">
                    <button
                      type="button"
                      onClick={() => void quickSwitch(acc)}
                      disabled={loading}
                      className="flex-1 flex items-center justify-between rounded-md border border-slate-200 px-3 py-2 text-sm hover:bg-slate-50 disabled:opacity-50"
                    >
                      <span className="text-slate-700">{acc.username}</span>
                      <span className="text-xs text-slate-400">
                        {acc.role === "admin" ? "管理员" : "员工"}
                        {fresh ? " · 免密进入" : " · 需验证密码"}
                      </span>
                    </button>
                    <button
                      type="button"
                      onClick={() => removeAccount(acc.userId)}
                      title="忘记此账号"
                      className="px-2 py-2 text-xs text-slate-300 hover:text-red-500"
                    >
                      ✕
                    </button>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
