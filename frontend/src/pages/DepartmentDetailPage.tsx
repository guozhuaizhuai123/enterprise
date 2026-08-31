import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import EmployeesTab from "../components/EmployeesTab";
import DocumentsTab from "../components/DocumentsTab";
import DepartmentMemoriesTab from "../components/DepartmentMemoriesTab";
import WorkSchedulesTab from "../components/WorkSchedulesTab";
import { listDepartments } from "../api/admin";
import type { Department } from "../types";

type Tab = "employees" | "schedules" | "documents" | "memories";

export default function DepartmentDetailPage() {
  const { departmentId } = useParams<{ departmentId: string }>();
  const [tab, setTab] = useState<Tab>("employees");
  const [dept, setDept] = useState<Department | null>(null);

  useEffect(() => {
    listDepartments().then((list) => {
      setDept(list.find((d) => d.id === departmentId) ?? null);
    });
  }, [departmentId]);

  if (!departmentId) return null;

  return (
    <div className="mx-auto w-full max-w-5xl">
      <Link to="/admin" className="text-sm text-slate-400 hover:text-slate-600">
        ← 返回部门列表
      </Link>
      <h2 className="text-lg font-semibold text-slate-900 mt-2 mb-4">{dept?.name ?? "部门详情"}</h2>

      <div className="flex gap-1 mb-4 border-b border-slate-200">
        <button
          onClick={() => setTab("employees")}
          className={`px-4 py-2 text-sm ${
            tab === "employees"
              ? "border-b-2 border-indigo-600 text-indigo-600 font-medium"
              : "text-slate-500 hover:text-slate-700"
          }`}
        >
          员工账号
        </button>
        <button
          onClick={() => setTab("schedules")}
          className={`px-4 py-2 text-sm ${tab === "schedules" ? "border-b-2 border-indigo-600 text-indigo-600 font-medium" : "text-slate-500 hover:text-slate-700"}`}
        >
          上班安排
        </button>
        <button
          onClick={() => setTab("memories")}
          className={`px-4 py-2 text-sm ${tab === "memories" ? "border-b-2 border-indigo-600 text-indigo-600 font-medium" : "text-slate-500 hover:text-slate-700"}`}
        >
          部门记忆
        </button>
        <button
          onClick={() => setTab("documents")}
          className={`px-4 py-2 text-sm ${
            tab === "documents"
              ? "border-b-2 border-indigo-600 text-indigo-600 font-medium"
              : "text-slate-500 hover:text-slate-700"
          }`}
        >
          知识文档
        </button>
      </div>

      {tab === "employees" ? (
        <EmployeesTab departmentId={departmentId} />
      ) : tab === "schedules" ? (
        <WorkSchedulesTab departmentId={departmentId} />
      ) : tab === "documents" ? (
        <DocumentsTab departmentId={departmentId} />
      ) : (
        <DepartmentMemoriesTab departmentId={departmentId} />
      )}
    </div>
  );
}
