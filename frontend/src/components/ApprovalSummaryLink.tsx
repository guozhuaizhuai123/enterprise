import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { listApprovalInbox, listSubmittedApprovals } from "../api/approvals";
import { formatApprovalCounts } from "../approvalFormat";

/**
 * 员工端顶栏的「审批中心」入口。
 * 顶栏只显示名称 + 待我审批消息数徽标，点击进入审批中心后再看详情，避免顶栏堆砌一堆数字。
 */
export default function ApprovalSummaryLink({ to = "/approvals" }: { to?: string }) {
  const [counts, setCounts] = useState<{ inbox: number; submitted: number } | null>(null);
  const location = useLocation();

  useEffect(() => {
    let active = true;
    async function refresh() {
      try {
        const [inbox, submitted] = await Promise.all([
          listApprovalInbox(),
          listSubmittedApprovals(),
        ]);
        if (active) setCounts({ inbox: inbox.length, submitted: submitted.length });
      } catch {
        if (active) setCounts(null);
      }
    }
    void refresh();
    const timer = window.setInterval(() => void refresh(), 15_000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  const selected = location.pathname === to;
  const pending = counts?.inbox ?? 0;
  const hasPending = pending > 0;

  return (
    <Link
      to={to}
      title={counts ? formatApprovalCounts(counts.inbox, counts.submitted) : "加载中…"}
      className={`flex items-center gap-2 rounded-full border px-3 py-1 text-xs transition ${
        selected
          ? "border-indigo-300 bg-indigo-50 text-indigo-700"
          : hasPending
            ? "border-rose-200 bg-rose-50 text-rose-700 hover:bg-rose-100"
            : "border-slate-200 bg-slate-50 text-slate-400 hover:bg-slate-100"
      }`}
    >
      <span
        className={`h-2 w-2 rounded-full ${
          hasPending && !selected ? "animate-pulse bg-rose-500" : selected ? "bg-indigo-500" : "bg-slate-300"
        }`}
      />
      <span className="font-medium">审批中心</span>
      {hasPending && (
        <span className="inline-flex min-w-[18px] h-[18px] items-center justify-center rounded-full bg-rose-500 px-1 text-[11px] font-semibold leading-none text-white">
          {pending}
        </span>
      )}
    </Link>
  );
}
