import type { ApprovalInstance, ApprovalRouteStep, ExpenseClaim } from "../types";
import { approvalProgressModel, formatApprovalAction, formatApprovalStatus } from "../approvalFormat";

function handlers(step: ApprovalRouteStep | undefined): string {
  return step?.handlers.map((item) => `${item.display_name}（${item.username}）`).join("、") ?? "";
}

function stepStatus(step: ApprovalRouteStep): string {
  if (step.status === "approved") return "已完成";
  if (step.status === "pending") return "当前处理";
  if (step.status === "rejected") return "已驳回";
  if (step.status === "cancelled") return "已撤回";
  return "待开始";
}

function stepTone(step: ApprovalRouteStep): string {
  if (step.status === "approved") return "border-emerald-200 bg-emerald-50 text-emerald-800";
  if (step.status === "pending") return "border-indigo-300 bg-indigo-50 text-indigo-900 ring-2 ring-indigo-100";
  if (step.status === "rejected") return "border-red-200 bg-red-50 text-red-800";
  if (step.status === "cancelled") return "border-slate-200 bg-slate-50 text-slate-600";
  return "border-slate-200 bg-white text-slate-500";
}

function statusBadge(instance: ApprovalInstance, expenseStatus?: ExpenseClaim["status"]): string {
  if (expenseStatus === "paid") return "已付款";
  if (expenseStatus === "payment_pending") return "待付款";
  return formatApprovalStatus(instance.status);
}

export default function ApprovalProgress({
  instance,
  expenseStatus,
}: {
  instance: ApprovalInstance;
  expenseStatus?: ExpenseClaim["status"];
}) {
  const route = instance.approval_route ?? [];
  const model = approvalProgressModel(instance.status, route, expenseStatus);
  const current = model.current;
  const upcoming = model.upcoming;
  const progress = route.length > 0 ? Math.round((model.completed.length / route.length) * 100) : 0;
  const currentHandlers = handlers(current);
  const currentDescription = current
    ? currentHandlers || "系统自动处理"
    : model.outcome === "审批已通过" || model.outcome === "已付款"
      ? "所有节点已完成"
      : model.outcome;

  return (
    <section className="mt-5 rounded-lg border border-indigo-100 bg-indigo-50/40 p-4" aria-label="审批进度">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold text-slate-800">审批进度</h3>
        </div>
        <span className="rounded-full bg-white px-2.5 py-1 text-xs font-medium text-slate-600">{statusBadge(instance, expenseStatus)}</span>
      </div>

      <div className="mt-4 rounded-md bg-white/80 p-3">
        <div className="flex items-center justify-between text-xs text-slate-500">
          <span>流程完成度</span>
          <span>{model.completed.length}/{route.length || 0} 个节点 · {progress}%</span>
        </div>
        <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100">
          <div className="h-full rounded-full bg-indigo-500 transition-all" style={{ width: `${progress}%` }} />
        </div>
      </div>

      <div className="mt-3 grid gap-2 sm:grid-cols-3">
        <div className="rounded-md border border-indigo-200 bg-white p-3">
          <div className="text-xs font-medium text-indigo-600">当前卡点</div>
          <div className="mt-1 text-sm font-semibold text-indigo-950">{current?.name ?? currentDescription}</div>
          <div className="mt-1 text-xs text-slate-500">{current ? currentDescription : "当前没有待处理节点"}</div>
        </div>
        <div className="rounded-md border border-slate-200 bg-white p-3">
          <div className="text-xs font-medium text-slate-500">后续节点</div>
          {upcoming.length > 0 ? (
            <div className="mt-1 space-y-1">
              {upcoming.map((step) => <div key={`${step.sequence}-${step.name}`} className="text-sm font-medium text-slate-700">{step.name}<span className="ml-1 text-xs font-normal text-slate-400">{handlers(step) || "系统处理"}</span></div>)}
            </div>
          ) : (
            <div className="mt-1 text-sm font-medium text-slate-700">无后续节点</div>
          )}
          <div className="mt-1 text-xs text-slate-400">{upcoming.length > 0 ? "当前节点完成后按顺序流转" : "流程已到最后一步"}</div>
        </div>
        <div className="rounded-md border border-emerald-200 bg-white p-3">
          <div className="text-xs font-medium text-emerald-600">最终结果</div>
          <div className="mt-1 text-sm font-semibold text-emerald-950">{model.outcome}</div>
          <div className="mt-1 text-xs text-slate-500">{expenseStatus === "paid" ? "付款记录已完成" : current ? "等待当前节点处理" : "审批链路已结束"}</div>
        </div>
      </div>

      <div className="mt-5">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">审批链路</h4>
        <ol className="mt-3 space-y-2">
          {route.map((step, index) => (
            <li key={`${step.sequence}-${step.name}`} className="flex gap-3">
              <div className="flex w-6 shrink-0 flex-col items-center">
                <span className={`flex h-6 w-6 items-center justify-center rounded-full border text-[11px] font-semibold ${stepTone(step)}`}>{step.status === "approved" ? "✓" : index + 1}</span>
                {index < route.length - 1 && <span className={`mt-1 h-full min-h-4 w-px ${step.status === "approved" ? "bg-emerald-200" : "bg-slate-200"}`} />}
              </div>
              <div className={`mb-1 min-w-0 flex-1 rounded-md border px-3 py-2 ${stepTone(step)}`}>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="text-sm font-medium">{step.name}</div>
                  <span className="text-xs font-medium">{stepStatus(step)}</span>
                </div>
                <div className="mt-1 text-xs opacity-75">
                  {step.status === "pending" ? (handlers(step) || "系统自动处理") : handlers(step) ? `处理人：${handlers(step)}` : step.status === "upcoming" ? "节点启动后确定处理人" : "系统已记录处理结果"}
                </div>
              </div>
            </li>
          ))}
        </ol>
      </div>

      {instance.actions.length > 0 && (
        <div className="mt-5 border-t border-indigo-100 pt-4">
          <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">处理记录</h4>
          <div className="mt-2 space-y-2">
            {instance.actions.map((action) => (
              <div key={action.id} className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 text-xs">
                <span className="text-slate-700"><strong>{action.actor_name || action.actor_id}</strong> · {formatApprovalAction(action.action)}</span>
                <time className="text-slate-400">{new Date(action.created_at).toLocaleString()}</time>
                {action.comment && <span className="basis-full text-slate-500">{action.comment}</span>}
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
}
