import { useState } from "react";
import { formatLeaveRange, formatWeeklySchedule } from "../scheduleFormat";
import { getWorkScheduleCardView } from "../workScheduleCardState";
import type { MyWorkSchedule } from "../types";

export default function WorkScheduleCard({
  schedule,
  onOpenHistory,
}: {
  schedule: MyWorkSchedule | null;
  onOpenHistory: () => void;
}) {
  const [collapsed, setCollapsed] = useState(false);
  const view = getWorkScheduleCardView(collapsed);

  if (!schedule) {
    return <div className="border-b border-slate-200 bg-white px-6 py-3 text-xs text-slate-400">正在加载我的上班安排...</div>;
  }

  return (
    <div className="border-b border-slate-200 bg-white px-6 py-3">
      <div className="flex items-center justify-between gap-3">
        <span className="font-medium text-slate-700">我的上班安排</span>
        <div className="flex items-center gap-2">
          <button onClick={onOpenHistory} className="rounded-md border border-slate-200 px-2.5 py-1 text-xs text-slate-500 hover:border-indigo-200 hover:text-indigo-600">请假与考勤历史</button>
          <button type="button" aria-expanded={!collapsed} onClick={() => setCollapsed((current) => !current)} className="rounded-md px-2.5 py-1 text-xs text-slate-500 hover:bg-slate-50 hover:text-slate-800">{view.toggleLabel}</button>
        </div>
      </div>
      {view.showDetails && (
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
          <span className="text-slate-600">{formatWeeklySchedule(schedule.days)}</span>
          {schedule.holidays.map((holiday) => (
            <span key={holiday.id} className="rounded-full bg-sky-50 px-2.5 py-1 text-xs text-sky-700">
              {holiday.name} · {formatLeaveRange(holiday.start_date, holiday.end_date)} · {holiday.scope_type === "company" ? "全公司休假" : `${holiday.department_name}休假`}
            </span>
          ))}
          {schedule.leave_requests.map((item) => (
            <span
              key={item.id}
              className={`rounded-full px-2.5 py-1 text-xs ${
                item.status === "approved"
                  ? "bg-emerald-50 text-emerald-700"
                  : "bg-amber-50 text-amber-700"
              }`}
            >
              {item.leave_type} · {formatLeaveRange(item.start_date, item.end_date)} · {item.status === "approved" ? "已批准" : "待审批"}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
