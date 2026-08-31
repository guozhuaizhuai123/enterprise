import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { getDashboardOverview } from "../api/dashboard";
import { listAdminDocuments } from "../api/admin";
import { listOrgUnits } from "../api/organization";
import { listContracts, listProjects } from "../api/projects";
import { listAdminTickets, listAdminTodos } from "../api/tickets";
import { listPayrollRuns } from "../api/payroll";
import AccountSwitcher from "../components/AccountSwitcher";
import BackButton from "../components/BackButton";
import DashboardMetric from "../components/DashboardMetric";
import { buildDashboardExpenseHref, formatDashboardMoney } from "../dashboardFormat";
import { formatExpenseStatus } from "../expenseFormat";
import { usePolling } from "../hooks/usePolling";
import { useAuthStore } from "../store/auth";
import type { DashboardOverview, OrgUnit } from "../types";

interface WorkspaceStats {
  projects: number;
  activeProjects: number;
  contracts: number;
  documents: number;
  openTickets: number;
  openTodos: number;
  payrollStatus: string;
}

function firstDayOfMonth(): string {
  const today = new Date();
  return `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-01`;
}

export default function AdminDashboardPage() {
  const [overview, setOverview] = useState<DashboardOverview | null>(null);
  const [units, setUnits] = useState<OrgUnit[]>([]);
  const [workspaceStats, setWorkspaceStats] = useState<WorkspaceStats | null>(null);
  const [start, setStart] = useState(firstDayOfMonth());
  const [end, setEnd] = useState(new Date().toISOString().slice(0, 10));
  const [departmentId, setDepartmentId] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<"" | "permission" | "load">("");
  const location = useLocation();
  const navigate = useNavigate();
  const { logout } = useAuthStore();
  const insideAdmin = location.pathname.startsWith("/admin/");

  async function loadWorkspaceStats() {
    if (!insideAdmin) return;
    try {
      const [projects, contracts, documents, tickets, todos, payrollRuns] = await Promise.all([listProjects(), listContracts(), listAdminDocuments(), listAdminTickets(), listAdminTodos(), listPayrollRuns()]);
      const latestPayroll = payrollRuns[0];
      setWorkspaceStats({
        projects: projects.length,
        activeProjects: projects.filter((project) => project.status === "active").length,
        contracts: contracts.length,
        documents: documents.length,
        openTickets: tickets.filter((ticket) => !["completed", "closed", "cancelled", "rejected"].includes(ticket.status)).length,
        openTodos: todos.filter((todo) => todo.status === "pending" || todo.status === "in_progress").length,
        payrollStatus: latestPayroll?.status ?? "未生成",
      });
    } catch {
      setWorkspaceStats(null);
    }
  }

  async function load(options?: { silent?: boolean }) {
    const silent = options?.silent ?? false;
    if (!silent) {
      setLoading(true);
      setError("");
    }
    try {
      setOverview(await getDashboardOverview({ start, end, departmentId }));
      void loadWorkspaceStats();
    } catch (loadError) {
      const status = (loadError as { response?: { status?: number } }).response?.status;
      if (!silent) setError(status === 403 ? "permission" : "load");
    } finally {
      if (!silent) setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    listOrgUnits().then(setUnits).catch(() => setUnits([]));
    void loadWorkspaceStats();
    // Initial dashboard load only; filters are applied explicitly.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 静默自动轮询，不再在页面上展示刷新控件；系统自己知道更新。
  usePolling(() => load({ silent: true }), { interval: 10_000 });

  function signOut() { logout(); navigate("/login"); }

  const expenseBasePath = insideAdmin ? "/admin/expenses" : "/expenses";
  const expenseHref = (filters: { status?: string; month?: string } = {}) => buildDashboardExpenseHref(expenseBasePath, {
    ...filters,
    start: filters.month ? undefined : overview?.period_start,
    end: filters.month ? undefined : overview?.period_end,
    departmentId,
  });

  const content = <main className="mx-auto w-full max-w-7xl p-6">
    <div className="flex flex-wrap items-start justify-between gap-4"><div><h1 className="text-2xl font-semibold text-slate-900">管理驾驶舱</h1><p className="mt-1 text-sm text-slate-500">聚焦组织规模、费用流向与当前业务积压。</p></div><div className="flex flex-wrap items-center gap-2"><input type="date" className="rounded-md border border-slate-300 px-3 py-2 text-sm" value={start} onChange={(e) => setStart(e.target.value)} /><input type="date" className="rounded-md border border-slate-300 px-3 py-2 text-sm" value={end} onChange={(e) => setEnd(e.target.value)} />{units.length > 0 && <select className="rounded-md border border-slate-300 px-3 py-2 text-sm" value={departmentId} onChange={(e) => setDepartmentId(e.target.value)}><option value="">全部部门</option>{units.map((unit) => <option key={unit.id} value={unit.id}>{unit.name}</option>)}</select>}<button onClick={() => void load()} className="rounded-md bg-indigo-600 px-4 py-2 text-sm text-white">应用</button></div></div>

    {loading && <div className="mt-6 rounded-xl border border-slate-200 bg-white p-12 text-center text-sm text-slate-400">正在汇总经营数据...</div>}
    {error === "permission" && <div className="mt-6 rounded-xl border border-amber-200 bg-amber-50 p-8 text-center"><p className="font-medium text-amber-800">当前账号没有驾驶舱权限</p><p className="mt-1 text-sm text-amber-600">管理员、人事和财务可按各自数据范围查看。</p></div>}
    {error === "load" && <div className="mt-6 rounded-xl border border-red-200 bg-red-50 p-8 text-center"><p className="text-sm text-red-700">数据加载失败</p><button onClick={() => void load()} className="mt-3 text-sm font-medium text-red-700 underline">重试</button></div>}

    {!loading && !error && overview && <div className="mt-6 space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {overview.organization && <><DashboardMetric to={insideAdmin ? "/admin/organization?status=active" : "/organization?status=active"} label="在职员工" value={overview.organization.active_employees} detail={`${overview.organization.departments} 个启用部门`} tone="indigo" /><DashboardMetric to={insideAdmin ? "/admin" : "/organization"} label="部门数量" value={overview.organization.departments} detail="当前数据权限范围" /></>}
        <DashboardMetric to={insideAdmin ? "/admin/expenses?status=pending_approval" : "/expenses?status=pending_approval"} label="待审批" value={overview.approvals.pending} detail="点击查看待处理费用单" tone="amber" />
        <DashboardMetric to={insideAdmin ? "/admin/expenses?status=payment_pending" : "/expenses?status=payment_pending"} label="待付款金额" value={formatDashboardMoney(overview.expenses.payment_pending?.amount ?? "0.00")} detail={`${overview.expenses.payment_pending?.count ?? 0} 笔`} tone="emerald" />
      </div>

      {insideAdmin && workspaceStats && <section className="rounded-xl border border-slate-200 bg-white p-5"><div className="flex items-center justify-between"><div><h2 className="font-semibold text-slate-900">业务工作台</h2><p className="mt-1 text-xs text-slate-400">从这里直接进入各业务模块，数据与列表页实时同步。</p></div><Link to="/admin/organization" className="text-sm text-indigo-600">组织设置 →</Link></div><div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4"><DashboardMetric to="/admin/projects" label="项目" value={workspaceStats.projects} detail={`${workspaceStats.activeProjects} 个进行中`} tone="indigo" /><DashboardMetric to="/admin/contracts" label="合同" value={workspaceStats.contracts} detail="合同台账" tone="slate" /><DashboardMetric to="/admin/knowledge" label="知识文档" value={workspaceStats.documents} detail="可按项目/合同追踪" tone="slate" /><DashboardMetric to="/admin/tickets" label="协作待办" value={workspaceStats.openTickets + workspaceStats.openTodos} detail={`${workspaceStats.openTickets} 个工单 · ${workspaceStats.openTodos} 个待办`} tone="amber" /></div><div className="mt-3 flex flex-wrap gap-2 text-xs"><Link to="/admin/payroll" className="rounded-full border border-slate-200 px-3 py-1.5 text-slate-600 hover:bg-slate-50">薪酬发薪 · {workspaceStats.payrollStatus === "未生成" ? "未生成批次" : workspaceStats.payrollStatus === "paid" ? "已发放" : workspaceStats.payrollStatus === "approved" ? "待付款" : "处理中"}</Link><Link to="/admin/work-schedules" className="rounded-full border border-slate-200 px-3 py-1.5 text-slate-600 hover:bg-slate-50">排班与考勤</Link><Link to="/admin/sensitive-events" className="rounded-full border border-slate-200 px-3 py-1.5 text-slate-600 hover:bg-slate-50">敏感记录</Link></div></section>}

      <div className="grid gap-5 lg:grid-cols-[2fr_1fr]">
        <section className="rounded-xl border border-slate-200 bg-white p-5"><div className="flex items-center justify-between"><div><h2 className="font-semibold text-slate-900">费用状态分布</h2><p className="mt-1 text-xs text-slate-400">金额由服务端 Decimal 聚合 · {overview.period_start} 至 {overview.period_end} · 点击状态查看明细</p></div><Link to={expenseHref()} className="text-sm text-indigo-600">进入费用中心 →</Link></div><div className="mt-4 overflow-hidden rounded-lg border border-slate-200"><table className="w-full text-sm"><thead className="bg-slate-50 text-left text-xs text-slate-400"><tr><th className="px-4 py-2">状态</th><th className="px-4 py-2 text-right">单量</th><th className="px-4 py-2 text-right">金额</th></tr></thead><tbody>{Object.entries(overview.expenses).map(([status, bucket]) => {
          const target = expenseHref({ status });
          const label = formatExpenseStatus(status);
          return <tr key={status} role="link" tabIndex={0} aria-label={`查看${label}费用明细`} onClick={() => navigate(target)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") navigate(target); }} className="cursor-pointer border-t border-slate-100 transition hover:bg-indigo-50/60 focus:bg-indigo-50/60 focus:outline-none"><td className="px-4 py-2 font-medium text-indigo-700">{label} <span aria-hidden="true">→</span></td><td className="px-4 py-2 text-right text-slate-500">{bucket.count}</td><td className="px-4 py-2 text-right font-medium text-slate-800">{formatDashboardMoney(bucket.amount)}</td></tr>;
        })}</tbody></table></div></section>
        <section className="rounded-xl border border-slate-200 bg-white p-5"><h2 className="font-semibold text-slate-900">今日运营待办</h2><div className="mt-4 space-y-3"><DashboardMetric to={insideAdmin ? "/admin/work-schedules" : "/organization"} label="待处理请假" value={overview.operations.pending_leave_requests} tone="amber" /><DashboardMetric to={insideAdmin ? "/admin/work-schedules" : "/organization"} label="今日未登记考勤" value={overview.operations.attendance_missing_today} /><DashboardMetric to={insideAdmin ? "/admin/tickets" : "/collaboration"} label="未完成协作待办" value={overview.operations.unfinished_todos} tone="indigo" /></div></section>
      </div>

      <section className="rounded-xl border border-slate-200 bg-white p-5"><div><h2 className="font-semibold text-slate-900">月度费用趋势</h2><p className="mt-1 text-xs text-slate-400">点击月份查看当月全部费用明细</p></div>{overview.monthly_expenses.length === 0 ? <p className="py-8 text-center text-sm text-slate-400">当前区间暂无费用数据</p> : <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{overview.monthly_expenses.map((item) => <Link key={item.month} to={expenseHref({ month: item.month })} aria-label={`查看 ${item.month} 月费用明细`} className="group rounded-lg border border-slate-200 p-3 transition hover:border-indigo-300 hover:bg-indigo-50/60"><p className="text-xs text-slate-400 group-hover:text-indigo-600">{item.month} <span aria-hidden="true">→</span></p><p className="mt-1 font-semibold text-slate-800">{formatDashboardMoney(item.amount)}</p><p className="text-xs text-slate-400">{item.count} 笔</p></Link>)}</div>}</section>
      <p className="text-right text-xs text-slate-400">统计时区：{overview.timezone}</p>
    </div>}
  </main>;

  if (insideAdmin) return content;
  return <div className="min-h-screen bg-slate-50"><header className="flex items-center justify-between border-b border-slate-200 bg-white px-6 py-3"><div className="flex items-center gap-4"><BackButton fallback="/chat" /><span className="font-semibold text-slate-900">企业智能检索系统</span><Link to="/chat" className="text-sm text-slate-500">知识助手</Link><Link to="/expenses" className="text-sm text-slate-500">费用报销</Link></div><div className="flex items-center gap-3"><AccountSwitcher /><button onClick={signOut} className="text-sm text-slate-400">退出登录</button></div></header>{content}</div>;
}
