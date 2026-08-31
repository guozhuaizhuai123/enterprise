import WorkSchedulesTab from "../components/WorkSchedulesTab";

export default function WorkSchedulesPage() {
  return (
    <div className="mx-auto w-full max-w-6xl">
      <div className="mb-5">
        <h2 className="text-lg font-semibold text-slate-900">排班与请假审批</h2>
        <p className="mt-1 text-sm text-slate-400">统一管理公司假期、员工考勤、上班周期并处理请假申请。</p>
      </div>
      <WorkSchedulesTab />
    </div>
  );
}
