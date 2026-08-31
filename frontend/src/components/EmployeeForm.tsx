import { useEffect, useState } from "react";
import type {
  EmploymentStatus,
  OrgEmployee,
  OrgEmployeeInput,
  OrgEmployeeUpdate,
  OrgRole,
  OrgUnit,
} from "../types";

interface EmployeeFormProps {
  employee: OrgEmployee | null;
  units: OrgUnit[];
  employees: OrgEmployee[];
  busy: boolean;
  onSave: (data: OrgEmployeeInput | OrgEmployeeUpdate) => Promise<void>;
  onCancel: () => void;
}

const ROLE_OPTIONS: Array<{ value: OrgRole; label: string }> = [
  { value: "employee", label: "员工" },
  { value: "hr", label: "人事" },
  { value: "manager", label: "部门负责人" },
  { value: "finance", label: "财务" },
];

// 职级使用下拉选择，避免用户自由填写出现不一致（如 L2 / P2 / 二级 等）。
const LEVEL_OPTIONS: string[] = [
  "",
  "L1",
  "L2",
  "L3",
  "L4",
  "L5",
  "L6",
  "M1",
  "M2",
  "M3",
];

export default function EmployeeForm({
  employee,
  units,
  employees,
  busy,
  onSave,
  onCancel,
}: EmployeeFormProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [hireDate, setHireDate] = useState("");
  const [status, setStatus] = useState<EmploymentStatus>("active");
  const [position, setPosition] = useState("");
  const [level, setLevel] = useState("");
  const [managerId, setManagerId] = useState("");
  const [salary, setSalary] = useState("");
  const [notes, setNotes] = useState("");
  const [departmentIds, setDepartmentIds] = useState<string[]>([]);
  const [primaryDepartmentId, setPrimaryDepartmentId] = useState("");
  const [roles, setRoles] = useState<OrgRole[]>(["employee"]);
  const [validation, setValidation] = useState("");

  useEffect(() => {
    setUsername(employee?.username ?? "");
    setPassword("");
    setFullName(employee?.full_name ?? "");
    setPhone(employee?.phone ?? "");
    setEmail(employee?.email ?? "");
    setHireDate(employee?.hire_date ?? "");
    setStatus(employee?.status ?? "active");
    setPosition(employee?.position ?? "");
    setLevel(employee?.level ?? "");
    setManagerId(employee?.manager_id ?? "");
    setSalary(employee?.salary ?? "");
    setNotes(employee?.notes ?? "");
    const memberships = employee?.departments ?? [];
    setDepartmentIds(memberships.map((item) => item.department_id));
    setPrimaryDepartmentId(
      memberships.find((item) => item.is_primary)?.department_id ?? memberships[0]?.department_id ?? "",
    );
    const nextRoles = (employee?.roles ?? ["employee"]).filter(
      (role): role is OrgRole => ROLE_OPTIONS.some((option) => option.value === role),
    );
    setRoles(nextRoles.length ? nextRoles : ["employee"]);
    setValidation("");
  }, [employee]);

  function toggleDepartment(id: string, checked: boolean) {
    const next = checked
      ? [...departmentIds, id]
      : departmentIds.filter((departmentId) => departmentId !== id);
    setDepartmentIds(next);
    if (!next.includes(primaryDepartmentId)) setPrimaryDepartmentId(next[0] ?? "");
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!fullName.trim() || departmentIds.length === 0 || !primaryDepartmentId) {
      setValidation("请填写姓名，并至少选择一个主部门");
      return;
    }
    if (!employee && (!username.trim() || password.length < 8)) {
      setValidation("新员工需填写用户名，初始密码至少 8 位");
      return;
    }
    setValidation("");
    const common = {
      full_name: fullName.trim(),
      phone: phone.trim(),
      email: email.trim(),
      hire_date: hireDate || null,
      status,
      position: position.trim(),
      level: level.trim(),
      manager_id: managerId || null,
      salary: salary.trim(),
      department_ids: departmentIds,
      primary_department_id: primaryDepartmentId,
      roles,
    };
    if (employee) {
      await onSave({ ...common, notes: notes.trim() });
    } else {
      await onSave({ ...common, username: username.trim(), password });
    }
  }

  const inputClass =
    "w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-100";

  return (
    <form onSubmit={submit} className="space-y-5">
      <div className="grid grid-cols-2 gap-4">
        <label className="text-sm text-slate-600">
          登录账号
          <input className={`${inputClass} mt-1`} value={username} onChange={(e) => setUsername(e.target.value)} disabled={Boolean(employee)} />
        </label>
        {!employee && (
          <label className="text-sm text-slate-600">
            初始密码
            <input type="password" autoComplete="new-password" className={`${inputClass} mt-1`} value={password} onChange={(e) => setPassword(e.target.value)} />
          </label>
        )}
        <label className="text-sm text-slate-600">
          姓名
          <input className={`${inputClass} mt-1`} value={fullName} onChange={(e) => setFullName(e.target.value)} />
        </label>
        <label className="text-sm text-slate-600">
          在职状态
          <select className={`${inputClass} mt-1`} value={status} onChange={(e) => setStatus(e.target.value as EmploymentStatus)}>
            <option value="probation">试用期</option>
            <option value="active">在职</option>
            <option value="suspended">停职</option>
            <option value="terminated">已离职</option>
          </select>
        </label>
        <label className="text-sm text-slate-600">
          手机
          <input className={`${inputClass} mt-1`} value={phone} onChange={(e) => setPhone(e.target.value)} />
        </label>
        <label className="text-sm text-slate-600">
          邮箱
          <input type="email" className={`${inputClass} mt-1`} value={email} onChange={(e) => setEmail(e.target.value)} />
        </label>
        <label className="text-sm text-slate-600">
          入职日期
          <input type="date" className={`${inputClass} mt-1`} value={hireDate} onChange={(e) => setHireDate(e.target.value)} />
        </label>
        <label className="text-sm text-slate-600">
          直属上级
          <select className={`${inputClass} mt-1`} value={managerId} onChange={(e) => setManagerId(e.target.value)}>
            <option value="">未设置</option>
            {employees.filter((item) => item.id !== employee?.id && item.status !== "terminated").map((item) => (
              <option key={item.id} value={item.id}>{item.full_name || item.username}</option>
            ))}
          </select>
        </label>
        <label className="text-sm text-slate-600">
          岗位
          <input className={`${inputClass} mt-1`} value={position} onChange={(e) => setPosition(e.target.value)} />
        </label>
        <label className="text-sm text-slate-600">
          职级
          <select className={`${inputClass} mt-1`} value={level} onChange={(e) => setLevel(e.target.value)}>
            {LEVEL_OPTIONS.map((option) => (
              <option key={option} value={option}>{option === "" ? "未设置" : option}</option>
            ))}
          </select>
        </label>
        <label className="text-sm text-slate-600">
          薪资
          <input className={`${inputClass} mt-1`} value={salary} onChange={(e) => setSalary(e.target.value)} placeholder="如：18K / 18000" />
        </label>
      </div>

      <fieldset>
        <legend className="text-sm font-medium text-slate-700">所属部门</legend>
        <div className="mt-2 grid grid-cols-2 gap-2 rounded-lg border border-slate-200 p-3">
          {units.filter((unit) => unit.active).map((unit) => (
            <label key={unit.id} className="flex items-center gap-2 text-sm text-slate-600">
              <input type="checkbox" checked={departmentIds.includes(unit.id)} onChange={(e) => toggleDepartment(unit.id, e.target.checked)} />
              {unit.name} <span className="text-xs text-slate-400">{unit.code}</span>
              {departmentIds.includes(unit.id) && (
                <input type="radio" name="primary-department" aria-label={`${unit.name}设为主部门`} checked={primaryDepartmentId === unit.id} onChange={() => setPrimaryDepartmentId(unit.id)} />
              )}
            </label>
          ))}
        </div>
        <p className="mt-1 text-xs text-slate-400">勾选部门后，用右侧圆点指定主部门。</p>
      </fieldset>

      <fieldset>
        <legend className="text-sm font-medium text-slate-700">业务角色</legend>
        <div className="mt-2 flex flex-wrap gap-4">
          {ROLE_OPTIONS.map((option) => (
            <label key={option.value} className="flex items-center gap-2 text-sm text-slate-600">
              <input
                type="checkbox"
                checked={roles.includes(option.value)}
                onChange={(e) => setRoles((current) => e.target.checked ? [...current, option.value] : current.filter((role) => role !== option.value))}
              />
              {option.label}
            </label>
          ))}
        </div>
      </fieldset>

      {employee && (
        <label className="block text-sm text-slate-600">
          备注
          <textarea className={`${inputClass} mt-1 min-h-20`} value={notes} onChange={(e) => setNotes(e.target.value)} />
        </label>
      )}

      {validation && <p className="text-sm text-red-600">{validation}</p>}
      <div className="flex justify-end gap-3 border-t border-slate-100 pt-4">
        <button type="button" onClick={onCancel} className="rounded-md px-4 py-2 text-sm text-slate-500 hover:bg-slate-100">取消</button>
        <button type="submit" disabled={busy} className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50">
          {busy ? "保存中..." : employee ? "保存档案" : "创建员工"}
        </button>
      </div>
    </form>
  );
}
