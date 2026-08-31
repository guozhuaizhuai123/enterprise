import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { generatePayroll, getPayrollSettings, listPayrollRuns, updatePayrollSettings } from "../api/payroll";
import type { PayrollRun, PayrollSetting } from "../types";

function errorMessage(error: unknown): string {
  return (error as { response?: { data?: { detail?: string } } }).response?.data?.detail || "操作失败，请稍后重试";
}

const statusLabels: Record<string, string> = {
  pending_approval: "审批中", approved: "已审批", rejected: "已驳回", paid: "已发放", generated: "已生成",
};

export default function PayrollPage() {
  const [settings, setSettings] = useState<PayrollSetting | null>(null);
  const [runs, setRuns] = useState<PayrollRun[]>([]);
  const [payDay, setPayDay] = useState(10);
  const [leadDays, setLeadDays] = useState(5);
  const [autoEnabled, setAutoEnabled] = useState(true);
  const [period, setPeriod] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function refresh() {
    setLoading(true);
    try {
      const [nextSettings, nextRuns] = await Promise.all([getPayrollSettings(), listPayrollRuns()]);
      setSettings(nextSettings); setRuns(nextRuns); setPayDay(nextSettings.pay_day); setLeadDays(nextSettings.generation_lead_days); setAutoEnabled(nextSettings.auto_enabled);
    } catch (loadError) { setError(errorMessage(loadError)); } finally { setLoading(false); }
  }
  useEffect(() => { void refresh(); }, []);

  const nextRun = useMemo(() => {
    if (!settings) return "";
    const now = new Date();
    const pay = new Date(now.getFullYear(), now.getMonth(), Math.min(settings.pay_day, 28));
    if (now.getDate() > pay.getDate()) pay.setMonth(pay.getMonth() + 1);
    const due = new Date(pay); due.setDate(due.getDate() - settings.generation_lead_days);
    return `${due.getFullYear()}-${String(due.getMonth() + 1).padStart(2, "0")}-${String(due.getDate()).padStart(2, "0")}`;
  }, [settings]);

  async function saveSettings(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError(""); setMessage("");
    try { const saved = await updatePayrollSettings({ auto_enabled: autoEnabled, pay_day: payDay, generation_lead_days: leadDays }); setSettings(saved); setMessage("工资设置已保存"); }
    catch (saveError) { setError(errorMessage(saveError)); } finally { setBusy(false); }
  }
  async function createRun() {
    setBusy(true); setError(""); setMessage("");
    try { await generatePayroll(period || undefined); setPeriod(""); setMessage("工资费用单已生成并提交财务审批"); await refresh(); }
    catch (generateError) { setError(errorMessage(generateError)); } finally { setBusy(false); }
  }

  return <div className="mx-auto max-w-7xl space-y-6">
    <div><h1 className="text-2xl font-semibold text-slate-900">薪酬与发薪</h1><p className="mt-1 text-sm text-slate-500">统一设置发薪日、提前生成账单，并追踪工资审批状态。</p></div>
    {error && <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}
    {message && <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{message}</div>}
    <section className="grid gap-6 lg:grid-cols-[1fr_1.4fr]">
      <form onSubmit={saveSettings} className="rounded-xl border border-slate-200 bg-white p-5 space-y-4">
        <div><h2 className="font-semibold text-slate-900">发薪规则</h2><p className="mt-1 text-xs text-slate-500">工资期间按自然月计算，发薪日支付上一个月工资。</p></div>
        <label className="flex items-center justify-between rounded-lg bg-slate-50 px-3 py-3 text-sm"><span>启用自动生成</span><input type="checkbox" checked={autoEnabled} onChange={(e) => setAutoEnabled(e.target.checked)} /></label>
        <label className="block text-sm text-slate-600">每月发薪日<input type="number" min="1" max="28" value={payDay} onChange={(e) => setPayDay(Number(e.target.value))} className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2" /></label>
        <label className="block text-sm text-slate-600">提前生成费用账单（天）<input type="number" min="0" max="31" value={leadDays} onChange={(e) => setLeadDays(Number(e.target.value))} className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2" /></label>
        <p className="text-xs text-slate-500">下一次预计生成：<span className="font-medium text-slate-700">{nextRun || "加载中"}</span></p>
        <button disabled={busy || loading} className="w-full rounded-md bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50">保存发薪规则</button>
      </form>
      <div className="rounded-xl border border-slate-200 bg-white p-5">
        <div className="flex flex-wrap items-end justify-between gap-3"><div><h2 className="font-semibold text-slate-900">工资批次</h2><p className="mt-1 text-xs text-slate-500">生成后由系统完成内部审核，并进入费用付款队列。</p></div><div className="flex gap-2"><input value={period} onChange={(e) => setPeriod(e.target.value)} placeholder="指定期间 YYYY-MM" className="w-36 rounded-md border border-slate-300 px-2 py-2 text-sm" /><button onClick={() => void createRun()} disabled={busy} className="rounded-md border border-indigo-200 px-3 py-2 text-sm font-medium text-indigo-700 hover:bg-indigo-50 disabled:opacity-50">立即生成</button></div></div>
        {runs.length === 0 ? <p className="py-12 text-center text-sm text-slate-400">暂未生成工资批次</p> : <div className="mt-4 overflow-x-auto"><table className="w-full text-left text-sm"><thead className="border-b border-slate-100 text-xs text-slate-400"><tr><th className="py-2">工资期间</th><th>发薪日</th><th>人数</th><th>金额</th><th>状态</th><th>费用单</th></tr></thead><tbody>{runs.map((run) => <tr key={run.id} className="border-b border-slate-50"><td className="py-3 font-medium text-slate-800">{run.period}</td><td>{run.pay_date}</td><td>{run.lines.length}</td><td>¥{run.total_amount}</td><td><span className="rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-600">{statusLabels[run.status] || run.status}</span></td><td>{run.expense_claim_id ? <Link className="text-indigo-600 hover:underline" to="/admin/expenses">查看费用单</Link> : "-"}</td></tr>)}</tbody></table></div>}
      </div>
    </section>
  </div>;
}
