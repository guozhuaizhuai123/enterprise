import { useEffect, useState } from "react";
import { useLocation, useSearchParams } from "react-router-dom";
import {
  approveApproval,
  cancelApproval,
  getApproval,
  listApprovalHistory,
  listApprovalInbox,
  listSubmittedApprovals,
  rejectApproval,
} from "../api/approvals";
import {
  defaultApprovalSelection,
  formatApprovalAction,
  formatApprovalStatus,
} from "../approvalFormat";
import ApprovalTimeline from "../components/ApprovalTimeline";
import EmployeeHeader from "../components/EmployeeHeader";
import { usePolling } from "../hooks/usePolling";
import { useAuthStore } from "../store/auth";
import type { ApprovalHistoryItem, ApprovalInstance, ApprovalTask } from "../types";

type ApprovalTab = "inbox" | "submitted" | "history";

function entityLabel(type: string): string {
  return type === "expense_claim" ? "费用报销" : type;
}

function actionBadgeClass(action: string): string {
  return action === "approve"
    ? "bg-emerald-100 text-emerald-700"
    : action === "reject"
      ? "bg-red-100 text-red-700"
      : "bg-slate-100 text-slate-600";
}

export default function ApprovalCenterPage({
  initialTab = "inbox",
}: {
  initialTab?: ApprovalTab;
}) {
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const { roles } = useAuthStore();
  const insideAdmin = location.pathname.startsWith("/admin/");

  // 注意：searchParams 必须在下面的 useState 初始化器之前声明，否则运行时 TDZ 报错导致整页白屏。
  const [tab, setTab] = useState<ApprovalTab>(() => {
    const requested = searchParams.get("tab");
    return requested === "inbox" || requested === "submitted" || requested === "history"
      ? requested
      : initialTab;
  });
  const [inbox, setInbox] = useState<ApprovalTask[]>([]);
  const [submitted, setSubmitted] = useState<ApprovalInstance[]>([]);
  const [history, setHistory] = useState<ApprovalHistoryItem[]>([]);
  const [selected, setSelected] = useState<ApprovalInstance | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [conflict, setConflict] = useState(false);

  // 固定后台轮询，避免手动刷新控件占用审批空间。
  usePolling(() => refresh({ silent: true }), { interval: 10_000, paused: busy });

  /** silent=true 用于后台轮询：不闪 loading、不弹错误，失败就等下一轮。 */
  async function refresh(options: { silent?: boolean } = {}) {
    const silent = options.silent ?? false;
    if (!silent) {
      setLoading(true);
      setError("");
    }
    try {
      const [nextInbox, nextSubmitted, nextHistory] = await Promise.all([
        listApprovalInbox(),
        listSubmittedApprovals(),
        listApprovalHistory(),
      ]);
      setInbox(nextInbox);
      setSubmitted(nextSubmitted);
      setHistory(nextHistory);
      const nextSelection = defaultApprovalSelection(
        selected?.id ?? null,
        tab,
        nextInbox.map((task) => task.instance_id),
        nextSubmitted.map((instance) => instance.id),
      );
      // 已选中时也要重拉详情，这样别人先一步处理掉也能立刻看到最新状态。
      const targetId = nextSelection ?? selected?.id ?? null;
      if (targetId) {
        try {
          setSelected(await getApproval(targetId));
        } catch {
          if (!silent) setError("审批详情加载失败，该审批可能已超出你的查看范围");
        }
      }
    } catch {
      if (!silent) setError("审批数据加载失败，请检查服务连接");
    } finally {
      if (!silent) setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
    const requested = searchParams.get("approval");
    if (requested) void openApproval(requested);
    // Initial route hydration only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function openApproval(id: string) {
    setError("");
    setConflict(false);
    try {
      setSelected(await getApproval(id));
    } catch {
      setError("无法打开审批详情，可能已超出你的查看范围");
    }
  }

  async function reloadSelected() {
    if (!selected) return;
    setSelected(await getApproval(selected.id));
    setConflict(false);
    await refresh();
  }

  async function act(action: "approve" | "reject" | "cancel", comment: string) {
    if (!selected) return;
    setBusy(true);
    setError("");
    setConflict(false);
    try {
      const updated = action === "approve"
        ? await approveApproval(selected.id, selected.version, comment)
        : action === "reject"
          ? await rejectApproval(selected.id, selected.version, comment)
          : await cancelApproval(selected.id, selected.version, comment);
      setSelected(updated);
      await refresh();
    } catch (actionError) {
      const status = (actionError as { response?: { status?: number } }).response?.status;
      if (status === 409) {
        setConflict(true);
        setError("审批状态已被其他人更新，请刷新后再操作");
      } else {
        setError("审批操作失败，请稍后重试");
      }
    } finally {
      setBusy(false);
    }
  }

  function chooseTab(nextTab: ApprovalTab) {
    setTab(nextTab);
    setSelected(null);
    const nextSelection = defaultApprovalSelection(
      null,
      nextTab,
      inbox.map((task) => task.instance_id),
      submitted.map((instance) => instance.id),
    );
    if (nextSelection) void openApproval(nextSelection);
  }

  const tabClass = (value: ApprovalTab) =>
    `px-5 py-3 text-sm font-medium ${tab === value ? "border-b-2 border-indigo-600 text-indigo-700" : "text-slate-500"}`;

  const content = (
    <main className="mx-auto w-full max-w-7xl p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">审批中心</h1>
          <p className="mt-1 text-sm text-slate-500">集中处理待办审批，跟踪自己发起的申请与审批记录。</p>
        </div>
      </div>
      {error && <div className="mt-4 flex items-center justify-between rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"><span>{error}</span>{conflict && <button onClick={() => void reloadSelected()} className="font-medium underline">重新加载最新状态</button>}</div>}

      <div className="mt-6 grid gap-5 lg:grid-cols-[minmax(0,1fr)_420px]">
        <section className="overflow-hidden rounded-xl border border-slate-200 bg-white">
          <div className="flex border-b border-slate-200">
            <button onClick={() => chooseTab("inbox")} className={tabClass("inbox")}>待我审批 <span className="ml-1 rounded-full bg-indigo-50 px-2 py-0.5 text-xs">{inbox.length}</span></button>
            <button onClick={() => chooseTab("submitted")} className={tabClass("submitted")}>我发起的申请 <span className="ml-1 rounded-full bg-indigo-50 px-2 py-0.5 text-xs">{submitted.length}</span></button>
            <button onClick={() => chooseTab("history")} className={tabClass("history")}>审批历史 <span className="ml-1 rounded-full bg-indigo-50 px-2 py-0.5 text-xs">{history.length}</span></button>
          </div>
          {loading ? (
            <p className="p-10 text-center text-sm text-slate-400">正在加载审批...</p>
          ) : tab === "inbox" ? (
            inbox.length === 0 ? <div className="p-10 text-center text-sm text-slate-400"><p>当前没有待审批事项</p>{roles.includes("finance") && <p className="mt-2 text-xs text-amber-600">报销需先由直属上级审批；通过后会自动进入你的财务复核待办。</p>}</div> :
              <div className="divide-y divide-slate-100">{inbox.map((task) => <button key={task.id} onClick={() => void openApproval(task.instance_id)} className={`flex w-full items-center justify-between p-4 text-left hover:bg-slate-50 ${selected?.id === task.instance_id ? "bg-indigo-50" : ""}`}><div><div className="font-medium text-slate-800">{entityLabel(task.entity_type)} · {task.node_name}</div><p className="mt-1 text-xs text-slate-400">申请人 {task.requester_name} · {new Date(task.created_at).toLocaleString()}</p></div><span className="text-sm text-indigo-600">处理</span></button>)}</div>
          ) : tab === "submitted" ? (
            submitted.length === 0 ? <p className="p-10 text-center text-sm text-slate-400">还没有发起过申请</p> :
              <div className="divide-y divide-slate-100">{submitted.map((instance) => { const route = instance.approval_route ?? []; const currentStep = route.find((step) => step.status === "pending") ?? route.find((step) => step.status === "upcoming"); return <button key={instance.id} onClick={() => void openApproval(instance.id)} className={`flex w-full items-center justify-between p-4 text-left hover:bg-slate-50 ${selected?.id === instance.id ? "bg-indigo-50" : ""}`}><div><div className="font-medium text-slate-800">{entityLabel(instance.entity_type)}</div><p className="mt-1 text-xs text-slate-400">{new Date(instance.submitted_at).toLocaleString()} · 单号 {instance.entity_id.slice(0, 8)}</p>{currentStep && <p className="mt-1 text-xs text-indigo-600">当前：{currentStep.name}{currentStep.handlers.length > 0 ? ` · ${currentStep.handlers.map((handler) => `${handler.display_name}（${handler.username}）`).join("、")}` : currentStep.status === "pending" ? " · 缺少处理人" : ""}</p>}</div><span className={`rounded-full px-2 py-1 text-xs ${instance.status === "approved" ? "bg-emerald-100 text-emerald-700" : instance.status === "rejected" ? "bg-red-100 text-red-700" : "bg-slate-100 text-slate-600"}`}>{formatApprovalStatus(instance.status)}</span></button>; })}</div>
          ) : (
            history.length === 0 ? <p className="p-10 text-center text-sm text-slate-400">还没有审批过任何申请</p> :
              <div className="divide-y divide-slate-100">{history.map((item) => (
                <button key={item.id} onClick={() => void openApproval(item.instance_id)} className={`flex w-full items-start justify-between gap-3 p-4 text-left hover:bg-slate-50 ${selected?.id === item.instance_id ? "bg-indigo-50" : ""}`}>
                  <div className="min-w-0">
                    <div className="font-medium text-slate-800">{entityLabel(item.entity_type)} · {item.node_name}</div>
                    <p className="mt-1 text-xs text-slate-400">申请人 {item.requester_name} · {new Date(item.created_at).toLocaleString()}</p>
                    {item.comment && <p className="mt-1 truncate text-xs text-slate-500">我的意见：{item.comment}</p>}
                  </div>
                  <div className="flex shrink-0 flex-col items-end gap-1">
                    <span className={`rounded-full px-2 py-1 text-xs ${actionBadgeClass(item.action)}`}>{formatApprovalAction(item.action)}</span>
                    <span className="text-xs text-slate-400">{formatApprovalStatus(item.instance_status)}</span>
                  </div>
                </button>
              ))}</div>
          )}
        </section>

        <aside className="min-h-96 rounded-xl border border-slate-200 bg-white p-5">
          {selected ? <><div className="mb-5 border-b border-slate-100 pb-4"><div className="flex items-center justify-between"><h2 className="font-semibold text-slate-900">{entityLabel(selected.entity_type)}审批</h2><span className="rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-600">{formatApprovalStatus(selected.status)}</span></div><p className="mt-2 text-xs text-slate-400">申请人：{selected.requester_name} · 流程：{selected.workflow_name}</p><p className="mt-1 text-xs text-slate-400">业务单号：{selected.entity_id}</p></div><ApprovalTimeline instance={selected} busy={busy} onAction={act} /></> : <div className="flex h-full min-h-80 items-center justify-center text-sm text-slate-400">选择一项审批查看详情</div>}
        </aside>
      </div>
    </main>
  );

  if (insideAdmin) return content;
  return (
    <div className="min-h-screen bg-slate-50">
      <EmployeeHeader />
      {content}
    </div>
  );
}
