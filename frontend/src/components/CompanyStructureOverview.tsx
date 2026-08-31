import { buildCompanyStructure } from "../companyStructure";
import type { OrgEmployee, OrgUnit } from "../types";

const ROLE_LABELS: Record<string, string> = {
  admin: "系统管理员",
  employee: "员工",
  hr: "人事",
  manager: "部门负责人",
  finance: "财务复核",
};

export default function CompanyStructureOverview({ units, employees }: { units: OrgUnit[]; employees: OrgEmployee[] }) {
  const structure = buildCompanyStructure(units, employees);
  const coveragePercent = structure.coverage.total
    ? Math.round((structure.coverage.filled / structure.coverage.total) * 100)
    : 0;

  return (
    <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="font-semibold text-slate-900">公司构成与关键岗位</h2>
          <p className="mt-1 text-sm text-slate-500">按职级查看人员、部门负责人和审批岗位是否齐备。</p>
        </div>
        <div className="min-w-48 rounded-lg bg-slate-50 px-4 py-3">
          <div className="flex items-center justify-between text-sm"><span className="text-slate-500">关键岗位完整度</span><strong className="text-slate-900">{structure.coverage.filled}/{structure.coverage.total}</strong></div>
          <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-200"><div className={`h-full rounded-full ${coveragePercent === 100 ? "bg-emerald-500" : "bg-amber-500"}`} style={{ width: `${coveragePercent}%` }} /></div>
        </div>
      </div>

      {structure.coverage.missing.length > 0 ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">缺少关键岗位：{structure.coverage.missing.join("、")}。相关审批可能无法继续流转。</div>
      ) : (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">关键岗位已齐备，直属上级审批和财务复核均有明确处理人。</div>
      )}

      <div className="rounded-lg border border-indigo-100 bg-indigo-50/60 px-4 py-3">
        <div className="text-xs font-medium text-indigo-700">费用报销流转</div>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-slate-700"><span className="rounded bg-white px-3 py-1.5">员工提交</span><span>→</span><span className="rounded bg-white px-3 py-1.5">直属上级审批</span><span>→</span><span className="rounded bg-white px-3 py-1.5">财务复核</span><span>→</span><span className="rounded bg-white px-3 py-1.5">待财务付款</span></div>
      </div>

      <div className="grid gap-3 lg:grid-cols-2 xl:grid-cols-3">
        {units.map((unit) => {
          const manager = employees.find((employee) => employee.id === unit.manager_id);
          const memberCount = employees.filter((employee) => employee.departments.some((membership) => membership.department_id === unit.id)).length;
          return <div key={unit.id} className="rounded-lg border border-slate-200 p-3"><div className="flex items-center justify-between"><span className="font-medium text-slate-800">{unit.name}</span><span className="text-xs text-slate-400">{unit.code || "未编码"}</span></div><p className="mt-2 text-sm text-slate-500">负责人：<span className={manager ? "text-slate-700" : "text-amber-700"}>{manager?.full_name || manager?.username || "缺员"}</span></p><p className="mt-1 text-xs text-slate-400">在册 {memberCount} 人</p></div>;
        })}
      </div>

      <div className="space-y-3">
        {structure.levels.map((group) => (
          <div key={group.level} className="grid gap-3 rounded-lg border border-slate-100 bg-slate-50/70 p-4 md:grid-cols-[140px_1fr]">
            <div><div className="font-semibold text-slate-800">{group.level} · {group.label}</div><div className="mt-1 text-xs text-slate-400">{group.people.length} 人</div></div>
            <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">{group.people.map((person) => <div key={person.id} className="rounded-md bg-white px-3 py-2 shadow-sm"><div className="font-medium text-slate-800">{person.full_name || person.username}</div><div className="text-xs text-slate-500">{person.position || "岗位未设置"} · @{person.username}</div><div className="mt-1 text-xs text-indigo-600">{person.roles.filter((role) => role !== "employee").map((role) => ROLE_LABELS[role] || role).join("、") || "员工"}</div></div>)}</div>
          </div>
        ))}
      </div>
    </section>
  );
}
