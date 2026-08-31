import { useEffect, useState } from "react";
import type { OrgEmployee, OrgUnit } from "../types";

export interface OrgUnitUpdateInput {
  name?: string;
  code?: string;
  parent_id?: string | null;
  manager_id?: string | null;
  active?: boolean;
}

interface OrgUnitEditorProps {
  unit: OrgUnit;
  units: OrgUnit[];
  employees: OrgEmployee[];
  busy: boolean;
  onSave: (data: OrgUnitUpdateInput) => Promise<void>;
  onCancel: () => void;
}

function employeeLabel(employee: OrgEmployee): string {
  return employee.full_name?.trim() || employee.username;
}

export default function OrgUnitEditor({
  unit,
  units,
  employees,
  busy,
  onSave,
  onCancel,
}: OrgUnitEditorProps) {
  const [name, setName] = useState(unit.name);
  const [code, setCode] = useState(unit.code ?? "");
  const [parentId, setParentId] = useState(unit.parent_id ?? "");
  const [managerId, setManagerId] = useState(unit.manager_id ?? "");
  const [active, setActive] = useState(unit.active);
  const [validation, setValidation] = useState("");

  useEffect(() => {
    setName(unit.name);
    setCode(unit.code ?? "");
    setParentId(unit.parent_id ?? "");
    setManagerId(unit.manager_id ?? "");
    setActive(unit.active);
    setValidation("");
  }, [unit]);

  const candidateParents = units.filter((item) => item.id !== unit.id && item.active);
  const candidateManagers = employees.filter((item) => item.status !== "terminated");

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!name.trim()) {
      setValidation("请填写部门名称");
      return;
    }
    if (!code.trim()) {
      setValidation("请填写部门编码");
      return;
    }
    setValidation("");
    await onSave({
      name: name.trim(),
      code: code.trim().toUpperCase(),
      parent_id: parentId || null,
      manager_id: managerId || null,
      active,
    });
  }

  const inputClass =
    "w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-100";

  return (
    <form onSubmit={submit} className="space-y-5">
      <div className="grid grid-cols-2 gap-4">
        <label className="text-sm text-slate-600">
          部门名称
          <input className={`${inputClass} mt-1`} value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="text-sm text-slate-600">
          部门编码
          <input className={`${inputClass} mt-1 uppercase`} value={code} onChange={(e) => setCode(e.target.value)} />
        </label>
        <label className="text-sm text-slate-600">
          上级部门
          <select className={`${inputClass} mt-1`} value={parentId} onChange={(e) => setParentId(e.target.value)}>
            <option value="">无（一级部门）</option>
            {candidateParents.map((item) => (
              <option key={item.id} value={item.id}>{item.name}</option>
            ))}
          </select>
        </label>
        <label className="text-sm text-slate-600">
          部门负责人
          <select className={`${inputClass} mt-1`} value={managerId} onChange={(e) => setManagerId(e.target.value)}>
            <option value="">未设置</option>
            {candidateManagers.map((item) => (
              <option key={item.id} value={item.id}>{employeeLabel(item)}</option>
            ))}
          </select>
        </label>
      </div>

      <label className="flex items-center gap-2 text-sm text-slate-600">
        <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />
        部门启用（停用后不出现在可选列表中）
      </label>

      {validation && <p className="text-sm text-red-600">{validation}</p>}
      <div className="flex justify-end gap-3 border-t border-slate-100 pt-4">
        <button type="button" onClick={onCancel} className="rounded-md px-4 py-2 text-sm text-slate-500 hover:bg-slate-100">取消</button>
        <button type="submit" disabled={busy} className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50">
          {busy ? "保存中..." : "保存设置"}
        </button>
      </div>
    </form>
  );
}
