import { useEffect, useMemo, useState } from "react";
import { useLocation, useSearchParams } from "react-router-dom";
import {
  cancelExpense,
  createExpense,
  getExpense,
  deleteExpense,
  listAdminExpenses,
  listExpenses,
  payExpense,
  submitExpense,
  updateExpense,
  uploadExpenseAttachment,
} from "../api/expenses";
import EmployeeHeader from "../components/EmployeeHeader";
import ExpenseForm from "../components/ExpenseForm";
import { expenseControls, formatExpenseError, formatExpenseStatus } from "../expenseFormat";
import { useAuthStore } from "../store/auth";
import { getApproval } from "../api/approvals";
import ApprovalProgress from "../components/ApprovalProgress";
import { matchesExpenseDateScope } from "../dashboardFormat";
import type { ApprovalInstance, ExpenseClaim, ExpenseDraft } from "../types";

function message(error: unknown): string {
  return formatExpenseError((error as { response?: { data?: { detail?: string } } }).response?.data?.detail);
}

export default function ExpensePage() {
  const [mine, setMine] = useState<ExpenseClaim[]>([]);
  const [managed, setManaged] = useState<ExpenseClaim[]>([]);
  const [tab, setTab] = useState<"mine" | "finance">("mine");
  const [statusFilter, setStatusFilter] = useState("");
  const [departmentFilter, setDepartmentFilter] = useState("");
  const [requesterFilter, setRequesterFilter] = useState("");
  const [amountMin, setAmountMin] = useState("");
  const [amountMax, setAmountMax] = useState("");
  const [dateFilter, setDateFilter] = useState("");
  const [monthFilter, setMonthFilter] = useState("");
  const [startFilter, setStartFilter] = useState("");
  const [endFilter, setEndFilter] = useState("");
  const [selected, setSelected] = useState<ExpenseClaim | null>(null);
  const [approvalDetail, setApprovalDetail] = useState<ApprovalInstance | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [payTarget, setPayTarget] = useState<ExpenseClaim | null>(null);
  const [paymentDate, setPaymentDate] = useState(new Date().toISOString().slice(0, 10));
  const [paymentMethod, setPaymentMethod] = useState("bank");
  const [paymentReference, setPaymentReference] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const { role, roles } = useAuthStore();
  const insideAdmin = location.pathname.startsWith("/admin/");
  const financeRole = role === "admin" || roles.includes("finance");
  const requestedStatus = searchParams.get("status") ?? "";
  const requestedDepartment = searchParams.get("department") ?? "";
  const requestedMonth = searchParams.get("month") ?? "";
  const requestedStart = searchParams.get("start") ?? "";
  const requestedEnd = searchParams.get("end") ?? "";
  const requestedExpense = searchParams.get("expense") ?? "";

  async function refresh() {
    setLoading(true);
    setError("");
    try {
      const own = await listExpenses();
      setMine(own);
      if (financeRole || insideAdmin) setManaged(await listAdminExpenses());
      if (selected) setSelected(own.find((item) => item.id === selected.id) ?? managed.find((item) => item.id === selected.id) ?? null);
    } catch (loadError) {
      setError(message(loadError));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
    // Initial data load only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (insideAdmin) setTab("finance");
    setStatusFilter(requestedStatus);
    setDepartmentFilter(requestedDepartment);
    setMonthFilter(requestedMonth);
    setStartFilter(requestedStart);
    setEndFilter(requestedEnd);
    if (requestedExpense) getExpense(requestedExpense).then(setSelected).catch(() => setError("无法打开报销详情"));
  }, [insideAdmin, requestedDepartment, requestedEnd, requestedExpense, requestedMonth, requestedStart, requestedStatus]);

  useEffect(() => {
    setApprovalDetail(null);
    if (selected?.approval_instance_id) {
      void getApproval(selected.approval_instance_id).then(setApprovalDetail).catch(() => setApprovalDetail(null));
    }
  }, [selected?.approval_instance_id, selected?.status, selected?.updated_at]);

  const current = tab === "finance" ? managed : mine;
  const visible = useMemo(() => current.filter((claim) => {
    const statusOk = !statusFilter || (statusFilter === "processed"
      ? ["rejected", "cancelled", "paid"].includes(claim.status)
      : claim.status === statusFilter);
    const departmentOk = !departmentFilter || claim.department_id === departmentFilter;
    const requesterOk = !requesterFilter || claim.requester_id === requesterFilter;
    const amount = Number(claim.total_amount);
    const minOk = amountMin.trim() === "" || amount >= Number(amountMin);
    const maxOk = amountMax.trim() === "" || amount <= Number(amountMax);
    const dateOk = matchesExpenseDateScope(claim.created_at, {
      date: dateFilter,
      month: monthFilter,
      start: startFilter,
      end: endFilter,
    });
    return statusOk && departmentOk && requesterOk && minOk && maxOk && dateOk;
  }), [current, dateFilter, departmentFilter, requesterFilter, amountMin, amountMax, statusFilter, monthFilter, startFilter, endFilter]);

  function resetFilters() {
    setStatusFilter("");
    setDepartmentFilter("");
    setRequesterFilter("");
    setAmountMin("");
    setAmountMax("");
    setDateFilter("");
    setMonthFilter("");
    setStartFilter("");
    setEndFilter("");
  }

  function switchTab(nextTab: "mine" | "finance") {
    setTab(nextTab);
    resetFilters();
    setSelected(null);
  }
  const departments = useMemo(() => {
    const map = new Map<string, string>();
    for (const claim of managed) {
      if (claim.department_id) map.set(claim.department_id, claim.department_name || claim.department_id);
    }
    return Array.from(map, ([id, name]) => ({ id, name }));
  }, [managed]);
  const requesters = useMemo(() => {
    const map = new Map<string, string>();
    for (const claim of managed) map.set(claim.requester_id, claim.requester_name || claim.requester_id);
    return Array.from(map, ([id, name]) => ({ id, name }));
  }, [managed]);

  async function saveDraft(draft: ExpenseDraft, files: File[]) {
    setBusy(true);
    setError("");
    try {
      const claim = selected ? await updateExpense(selected.id, draft) : await createExpense(draft);
      for (const file of files) await uploadExpenseAttachment(claim.id, file);
      setEditorOpen(false);
      setSelected(null);
      await refresh();
    } catch (saveError) {
      setError(message(saveError));
    } finally {
      setBusy(false);
    }
  }

  async function submit(claim: ExpenseClaim) {
    if (!window.confirm(`确认提交报销单 ${claim.claim_no}？提交后不能修改。`)) return;
    setBusy(true);
    setError("");
    try { await submitExpense(claim.id); await refresh(); } catch (submitError) { setError(message(submitError)); } finally { setBusy(false); }
  }

  async function remove(claim: ExpenseClaim) {
    if (!window.confirm("确认删除这份草稿？")) return;
    await deleteExpense(claim.id);
    setSelected(null);
    await refresh();
  }

  async function withdraw(claim: ExpenseClaim) {
    if (!window.confirm("确认撤回这份报销申请？")) return;
    setBusy(true);
    try { await cancelExpense(claim); setSelected(null); await refresh(); } catch (cancelError) { setError(message(cancelError)); } finally { setBusy(false); }
  }

  async function confirmPayment() {
    if (!payTarget || !paymentReference.trim()) return;
    setBusy(true);
    setError("");
    try {
      await payExpense(payTarget.id, { payment_date: paymentDate, method: paymentMethod, reference: paymentReference.trim(), expected_version: payTarget.version });
      setPayTarget(null);
      setPaymentReference("");
      await refresh();
    } catch (payError) {
      setError(message(payError));
    } finally {
      setBusy(false);
    }
  }

  const content = (
    <main className="mx-auto w-full max-w-7xl p-6">
      <div className="flex items-start justify-between"><div><h1 className="text-2xl font-semibold text-slate-900">费用报销</h1><p className="mt-1 text-sm text-slate-500">从票据录入、逐级审批到财务付款，全程可追踪。</p></div>{tab === "mine" && <button onClick={() => { setSelected(null); setEditorOpen(true); }} className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500">新建报销</button>}</div>
      {error && <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</div>}

      {financeRole && <div className="mt-5 space-y-3"><div className="flex flex-wrap items-center gap-2"><button onClick={() => switchTab("mine")} className={`rounded-md px-4 py-2 text-sm ${tab === "mine" ? "bg-indigo-600 text-white" : "bg-white text-slate-600"}`}>我的报销</button><button onClick={() => switchTab("finance")} className={`rounded-md px-4 py-2 text-sm ${tab === "finance" ? "bg-indigo-600 text-white" : "bg-white text-slate-600"}`}>费用处理台</button>{tab === "finance" && <span className="text-xs text-slate-400">审批、付款和历史统一查看</span>}</div>{tab === "finance" && <div className="flex flex-wrap gap-2"><button onClick={() => setStatusFilter("pending_approval")} className={`rounded-full border px-3 py-1.5 text-xs ${statusFilter === "pending_approval" ? "border-indigo-400 bg-indigo-50 text-indigo-700" : "border-slate-200 bg-white text-slate-600"}`}>待审批 · {managed.filter((item) => item.status === "pending_approval").length}</button><button onClick={() => setStatusFilter("processed")} className={`rounded-full border px-3 py-1.5 text-xs ${statusFilter === "processed" ? "border-indigo-400 bg-indigo-50 text-indigo-700" : "border-slate-200 bg-white text-slate-600"}`}>已处理 · {managed.filter((item) => ["rejected", "cancelled", "paid"].includes(item.status)).length}</button><button onClick={() => setStatusFilter("payment_pending")} className={`rounded-full border px-3 py-1.5 text-xs ${statusFilter === "payment_pending" ? "border-indigo-400 bg-indigo-50 text-indigo-700" : "border-slate-200 bg-white text-slate-600"}`}>待付款 · {managed.filter((item) => item.status === "payment_pending").length}</button><button onClick={() => setStatusFilter("paid")} className={`rounded-full border px-3 py-1.5 text-xs ${statusFilter === "paid" ? "border-indigo-400 bg-indigo-50 text-indigo-700" : "border-slate-200 bg-white text-slate-600"}`}>付款历史 · {managed.filter((item) => item.status === "paid").length}</button></div>}</div>}

      <section className="mt-5 overflow-hidden rounded-xl border border-slate-200 bg-white">
        <div className="flex flex-wrap items-center gap-3 border-b border-slate-100 p-4">
          <select className="rounded-md border border-slate-300 px-3 py-2 text-sm" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}><option value="">全部状态</option><option value="draft">草稿</option><option value="pending_approval">待审批</option><option value="processed">已处理</option><option value="rejected">已驳回</option><option value="payment_pending">待付款</option><option value="paid">付款历史</option><option value="cancelled">已撤回</option></select>
          {tab === "finance" && <select className="rounded-md border border-slate-300 px-3 py-2 text-sm" value={departmentFilter} onChange={(e) => setDepartmentFilter(e.target.value)}><option value="">全部部门</option>{departments.map((unit) => <option key={unit.id} value={unit.id}>{unit.name}</option>)}</select>}
          {tab === "finance" && <select className="rounded-md border border-slate-300 px-3 py-2 text-sm" value={requesterFilter} onChange={(e) => setRequesterFilter(e.target.value)}><option value="">全部申请人</option>{requesters.map((person) => <option key={person.id} value={person.id}>{person.name}</option>)}</select>}
          <div className="flex items-center gap-1">
            <input type="number" min="0" placeholder="金额 ≥" className="w-24 rounded-md border border-slate-300 px-2 py-2 text-sm" value={amountMin} onChange={(e) => setAmountMin(e.target.value)} />
            <span className="text-xs text-slate-400">—</span>
            <input type="number" min="0" placeholder="金额 ≤" className="w-24 rounded-md border border-slate-300 px-2 py-2 text-sm" value={amountMax} onChange={(e) => setAmountMax(e.target.value)} />
          </div>
          <input type="month" aria-label="费用月份" title="按月份筛选" className="rounded-md border border-slate-300 px-3 py-2 text-sm" value={monthFilter} onChange={(e) => setMonthFilter(e.target.value)} />
          <input type="date" aria-label="费用日期" title="按单日筛选" className="rounded-md border border-slate-300 px-3 py-2 text-sm" value={dateFilter} onChange={(e) => setDateFilter(e.target.value)} />
          {(startFilter || endFilter) && <span className="rounded-full bg-indigo-50 px-3 py-1.5 text-xs text-indigo-700">统计区间：{startFilter || "不限"} 至 {endFilter || "不限"}</span>}
          <button onClick={resetFilters} className="text-sm text-slate-400">清除筛选</button>
        </div>
        {loading ? <p className="p-10 text-center text-sm text-slate-400">正在加载报销数据...</p> : visible.length === 0 ? <p className="p-10 text-center text-sm text-slate-400">暂无符合条件的报销单</p> : <div className="overflow-x-auto"><table className="w-full text-sm"><thead className="bg-slate-50 text-left text-xs text-slate-400"><tr><th className="px-4 py-3">报销单</th>{tab === "finance" && <th className="px-4 py-3">申请人</th>}{tab === "finance" && <th className="px-4 py-3">部门</th>}<th className="px-4 py-3">项目</th><th className="px-4 py-3">金额</th><th className="px-4 py-3">状态</th><th className="px-4 py-3">提交时间</th><th className="px-4 py-3"></th></tr></thead><tbody>{visible.map((claim) => {
          const effectiveRole = role === "admin" ? "admin" : roles.includes("finance") ? "finance" : roles.includes("manager") ? "manager" : "employee";
          const controls = expenseControls(claim.status, effectiveRole);
          return <tr key={claim.id} className="border-t border-slate-100"><td className="px-4 py-3"><button onClick={() => setSelected(claim)} className="text-left"><div className="font-medium text-slate-800">{claim.title}</div><div className="text-xs text-slate-400">{claim.claim_no}</div></button></td>{tab === "finance" && <td className="px-4 py-3 text-slate-600">{claim.requester_name}</td>}{tab === "finance" && <td className="px-4 py-3 text-slate-500">{claim.department_name || claim.department_id || "—"}</td>}<td className="px-4 py-3 text-slate-500">{claim.project_code || "—"}</td><td className="px-4 py-3 font-medium text-slate-800">¥ {Number(claim.total_amount).toFixed(2)}</td><td className="px-4 py-3"><span className="rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-600">{formatExpenseStatus(claim.status)}</span></td><td className="px-4 py-3 text-slate-400">{claim.submitted_at ? new Date(claim.submitted_at).toLocaleDateString() : "未提交"}</td><td className="px-4 py-3 text-right">{tab === "mine" && controls.edit && <button onClick={() => { setSelected(claim); setEditorOpen(true); }} className="mr-3 text-indigo-600">编辑</button>}{tab === "mine" && controls.submit && <button disabled={busy} onClick={() => void submit(claim)} className="text-emerald-600">提交</button>}{tab === "finance" && controls.pay && <button onClick={() => setPayTarget(claim)} className="rounded bg-emerald-600 px-3 py-1.5 text-white">登记付款</button>}</td></tr>;
        })}</tbody></table></div>}
      </section>

      {selected && !editorOpen && <div className="fixed inset-0 z-40 flex justify-end bg-black/30" onClick={() => setSelected(null)}><aside className="h-full w-full max-w-lg overflow-y-auto bg-white p-6 shadow-xl" onClick={(e) => e.stopPropagation()}><div className="flex justify-between"><div><h2 className="text-xl font-semibold text-slate-900">{selected.title}</h2><p className="text-xs text-slate-400">{selected.claim_no}</p></div><button onClick={() => setSelected(null)} className="text-slate-400">关闭</button></div><div className="mt-5 rounded-lg bg-slate-50 p-4"><div className="flex justify-between"><span className="text-sm text-slate-500">报销金额</span><strong className="text-xl">¥ {Number(selected.total_amount).toFixed(2)}</strong></div><p className="mt-2 text-sm text-slate-600">{selected.purpose || "未填写报销事由"}</p></div><div className="mt-5 space-y-3">{selected.items.map((item, index) => <div key={item.id ?? index} className="flex justify-between border-b border-slate-100 pb-3 text-sm"><div><div className="text-slate-700">{item.category} · {item.vendor || "未填商户"}</div><div className="text-xs text-slate-400">{item.expense_date} {item.invoice_no ? `· 发票 ${item.invoice_no}` : ""}</div></div><span className="font-medium">¥ {Number(item.amount).toFixed(2)}</span></div>)}</div><p className="mt-4 text-sm text-slate-500">票据附件：{selected.attachments.length} 个</p>{selected.approval_instance_id && <>{approvalDetail ? <ApprovalProgress instance={approvalDetail} expenseStatus={selected.status} /> : <p className="mt-4 text-sm text-slate-500">正在加载审批进度...</p>}</>}<div className="mt-6 flex gap-2 border-t border-slate-100 pt-4">{selected.status === "draft" && <><button onClick={() => setEditorOpen(true)} className="rounded bg-indigo-600 px-3 py-2 text-sm text-white">编辑</button><button onClick={() => void remove(selected)} className="rounded border border-red-200 px-3 py-2 text-sm text-red-600">删除草稿</button></>}{selected.status === "pending_approval" && selected.requester_id === useAuthStore.getState().userId && <button disabled={busy} onClick={() => void withdraw(selected)} className="rounded border border-slate-300 px-3 py-2 text-sm text-slate-600">撤回申请</button>}</div></aside></div>}

      {editorOpen && <div className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-black/30 p-6"><div className="my-auto w-full max-w-5xl rounded-xl bg-white p-6 shadow-xl"><h2 className="mb-5 text-xl font-semibold">{selected ? "编辑报销草稿" : "新建报销"}</h2><ExpenseForm key={selected?.id ?? "new"} initial={selected} busy={busy} onSave={saveDraft} onCancel={() => { setEditorOpen(false); setSelected(null); }} /></div></div>}

      {payTarget && <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-6" onClick={() => setPayTarget(null)}><div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl" onClick={(e) => e.stopPropagation()}><h2 className="font-semibold text-slate-900">登记付款 · {payTarget.claim_no}</h2><p className="mt-2 text-2xl font-semibold">¥ {Number(payTarget.total_amount).toFixed(2)}</p><label className="mt-4 block text-sm text-slate-600">付款日期<input type="date" className="mt-1 w-full rounded border border-slate-300 px-3 py-2" value={paymentDate} onChange={(e) => setPaymentDate(e.target.value)} /></label><label className="mt-3 block text-sm text-slate-600">付款方式<select className="mt-1 w-full rounded border border-slate-300 px-3 py-2" value={paymentMethod} onChange={(e) => setPaymentMethod(e.target.value)}><option value="bank">银行转账</option><option value="cash">现金</option><option value="corporate_card">公司卡</option></select></label><label className="mt-3 block text-sm text-slate-600">付款流水号 / 参考号<input className="mt-1 w-full rounded border border-slate-300 px-3 py-2" value={paymentReference} onChange={(e) => setPaymentReference(e.target.value)} /></label><div className="mt-5 flex justify-end gap-2"><button onClick={() => setPayTarget(null)} className="px-3 py-2 text-sm text-slate-500">取消</button><button disabled={busy || !paymentReference.trim()} onClick={() => void confirmPayment()} className="rounded bg-emerald-600 px-4 py-2 text-sm text-white disabled:opacity-50">确认已付款</button></div></div></div>}
    </main>
  );

  if (insideAdmin) return content;
  return <div className="min-h-screen bg-slate-50"><EmployeeHeader />{content}</div>;
}
