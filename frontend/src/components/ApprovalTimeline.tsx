import { useState } from "react";
import {
  approvalConfirmation,
  formatApprovalAction,
  formatApprovalStatus,
  approvalRouteSummary,
  type ApprovalConfirmation,
  type ApprovalDecisionAction,
} from "../approvalFormat";
import type { ApprovalInstance } from "../types";

interface ApprovalTimelineProps {
  instance: ApprovalInstance;
  busy: boolean;
  onAction: (action: "approve" | "reject" | "cancel", comment: string) => Promise<void>;
}

export default function ApprovalTimeline({ instance, busy, onAction }: ApprovalTimelineProps) {
  const [comment, setComment] = useState("");
  const [validation, setValidation] = useState("");
  const [pending, setPending] = useState<ApprovalConfirmation | null>(null);
  const routeSummary = approvalRouteSummary(instance.approval_route);

  function requestAction(action: ApprovalDecisionAction) {
    if (action === "reject" && !comment.trim()) {
      setValidation("驳回时必须填写原因");
      return;
    }
    setValidation("");
    setPending(approvalConfirmation(action, comment.trim()));
  }

  async function confirmAction() {
    if (!pending) return;
    await onAction(pending.action, pending.comment);
    setComment("");
    setPending(null);
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-2 sm:grid-cols-3">
        <div className="rounded-lg bg-indigo-50 p-3"><div className="text-xs text-indigo-500">当前处理人</div><div className="mt-1 text-sm font-medium text-indigo-900">{routeSummary.current}</div></div>
        {routeSummary.next && <div className="rounded-lg bg-slate-50 p-3"><div className="text-xs text-slate-400">下一处理人</div><div className="mt-1 text-sm font-medium text-slate-700">{routeSummary.next}</div></div>}
        <div className="rounded-lg bg-emerald-50 p-3"><div className="text-xs text-emerald-500">最终付款人</div><div className="mt-1 text-sm font-medium text-emerald-800">{routeSummary.final}</div></div>
      </div>
      <div>
        <h3 className="text-sm font-semibold text-slate-800">完整流转链路</h3>
        <ol className="mt-3 space-y-3">
          {(instance.approval_route ?? []).map((step) => (
            <li key={`${step.sequence}-${step.name}`} className="flex gap-3">
              <span className={`mt-1 h-3 w-3 shrink-0 rounded-full ${step.status === "approved" ? "bg-emerald-500" : step.status === "rejected" ? "bg-red-500" : step.status === "cancelled" ? "bg-slate-300" : step.status === "pending" ? "bg-indigo-500 ring-4 ring-indigo-100" : "bg-slate-200"}`} />
              <div>
                <div className="text-sm font-medium text-slate-700">{step.name}</div>
                <div className={`text-xs ${step.handlers.length === 0 && step.status === "pending" ? "text-red-500" : "text-slate-400"}`}>{step.handlers.length > 0 ? step.handlers.map((handler) => `${handler.display_name}（${handler.username}）`).join("、") : step.status === "pending" ? "缺少处理人" : "系统自动流转"} · {step.status === "upcoming" ? "未开始" : formatApprovalStatus(step.status)}</div>
              </div>
            </li>
          ))}
        </ol>
      </div>

      <div>
        <h3 className="text-sm font-semibold text-slate-800">流转记录</h3>
        <div className="mt-3 space-y-3 border-l border-slate-200 pl-4">
          {instance.actions.map((action) => (
            <div key={action.id} className="text-sm">
              <div className="text-slate-700"><span className="font-medium">{action.actor_name || action.actor_id}</span> · {formatApprovalAction(action.action)}</div>
              {action.comment && <p className="mt-1 rounded bg-slate-50 px-2 py-1 text-slate-600">{action.comment}</p>}
              <time className="text-xs text-slate-400">{new Date(action.created_at).toLocaleString()}</time>
            </div>
          ))}
        </div>
      </div>

      {(instance.can_approve || instance.can_reject || instance.can_cancel) && (
        <div className="border-t border-slate-100 pt-4">
          <textarea className="min-h-20 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" placeholder="填写审批意见（驳回时必填）" value={comment} onChange={(e) => setComment(e.target.value)} />
          {validation && <p className="mt-1 text-xs text-red-600">{validation}</p>}
          <div className="mt-3 flex flex-wrap gap-2">
            {instance.can_approve && <button disabled={busy} onClick={() => requestAction("approve")} className="rounded-md bg-emerald-600 px-4 py-2 text-sm text-white hover:bg-emerald-500 disabled:opacity-50">通过</button>}
            {instance.can_reject && <button disabled={busy} onClick={() => requestAction("reject")} className="rounded-md bg-red-600 px-4 py-2 text-sm text-white hover:bg-red-500 disabled:opacity-50">驳回</button>}
            {instance.can_cancel && <button disabled={busy} onClick={() => requestAction("cancel")} className="rounded-md border border-slate-300 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-50">撤回申请</button>}
          </div>
        </div>
      )}

      {pending && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" onClick={() => !busy && setPending(null)}>
          <div role="dialog" aria-modal="true" aria-labelledby="approval-confirm-title" className="w-full max-w-sm rounded-xl bg-white p-6 shadow-xl" onClick={(event) => event.stopPropagation()}>
            <h3 id="approval-confirm-title" className="text-lg font-semibold text-slate-900">{pending.title}</h3>
            <p className="mt-2 text-sm text-slate-500">确认后将立即流转到下一审批节点，操作会记录在审批历史中。</p>
            {pending.comment && <p className="mt-3 rounded-md bg-slate-50 px-3 py-2 text-sm text-slate-600">审批意见：{pending.comment}</p>}
            <div className="mt-5 flex justify-end gap-2">
              <button disabled={busy} onClick={() => setPending(null)} className="rounded-md px-4 py-2 text-sm text-slate-500 hover:bg-slate-100 disabled:opacity-50">取消</button>
              <button disabled={busy} onClick={() => void confirmAction()} className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50">{busy ? "处理中..." : pending.confirmLabel}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
