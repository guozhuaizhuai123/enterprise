import { useEffect, useMemo, useState } from "react";
import type { Department, TicketPreview, TicketType, UserOption } from "../types";

interface Props {
  open: boolean;
  preview: TicketPreview | null;
  participants: UserOption[];
  departments: Department[];
  myDepartmentIds: string[];
  saving: boolean;
  error: string;
  onConfirm: (data: { ticket_type: TicketType; subject: string; description: string; target_user_id?: string; department_id?: string; requested_department_id?: string }) => void;
  onClose: () => void;
}

const typeLabels: Record<TicketType, string> = {
  same_department: "同部门协助",
  cross_department: "跨部门协助",
  question: "业务询问",
  issue: "问题反馈",
};

export default function TicketPreviewDialog({
  open,
  preview,
  participants,
  departments,
  myDepartmentIds,
  saving,
  error,
  onConfirm,
  onClose,
}: Props) {
  const [ticketType, setTicketType] = useState<TicketType>("same_department");
  const [subject, setSubject] = useState("");
  const [description, setDescription] = useState("");
  const [targetUserId, setTargetUserId] = useState("");
  const [requestedDeptId, setRequestedDeptId] = useState("");

  useEffect(() => {
    if (!open || !preview) return;
    setTicketType(preview.ticket_type ?? "same_department");
    setSubject(preview.subject ?? "");
    setDescription(preview.description ?? "");
    setTargetUserId("");
    setRequestedDeptId("");

    // 尝试按用户名匹配处理人
    if (preview.target_username) {
      const name = preview.target_username.toLowerCase();
      const matched = participants.find(
        (p) =>
          p.username.toLowerCase() === name ||
          (p.department_name?.toLowerCase() || "") === name,
      );
      if (matched) setTargetUserId(matched.id);
    }

    // 尝试按名称匹配跨部门协助的目标部门
    if (preview.department_name && preview.ticket_type === "cross_department") {
      const name = preview.department_name.toLowerCase();
      const matched = departments.find((d) => d.name.toLowerCase() === name);
      if (matched) setRequestedDeptId(matched.id);
    }
  }, [open, preview, participants, departments]);

  const crossDepartments = useMemo(
    () => departments.filter((d) => !myDepartmentIds.includes(d.id)),
    [departments, myDepartmentIds],
  );

  if (!open || !preview) return null;

  const canSubmit =
    subject.trim() &&
    description.trim() &&
    (ticketType !== "cross_department" || !!requestedDeptId);

  function confirm() {
    const baseDept = myDepartmentIds[0];
    // 处理人可选：未指定时交给管理员。同部门协助必须发给具体员工，
    // 因此「无处理人 + 同部门协助」降级为「问题反馈」并路由给管理员。
    let finalType = ticketType;
    const data: Parameters<Props["onConfirm"]>[0] = {
      ticket_type: finalType,
      subject: subject.trim(),
      description: description.trim(),
    };
    if (ticketType === "cross_department") {
      data.requested_department_id = requestedDeptId;
    } else if (ticketType === "same_department" && targetUserId) {
      data.department_id = baseDept;
      data.target_user_id = targetUserId;
    } else {
      if (ticketType === "same_department") finalType = "issue";
      data.ticket_type = finalType;
      data.department_id = baseDept;
      data.target_user_id = targetUserId || "admin";
    }
    onConfirm(data);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-lg rounded-xl bg-white p-6 shadow-lg">
        <h2 className="text-lg font-semibold text-slate-900">确认发起工单</h2>
        <p className="mt-1 text-sm text-slate-500">已从对话中提取信息，请核对后提交</p>

        <div className="mt-4 space-y-3">
          <div>
            <label className="block text-sm text-slate-600 mb-1">工单类型</label>
            <select
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
              value={ticketType}
              onChange={(e) => setTicketType(e.target.value as TicketType)}
            >
              {Object.entries(typeLabels).map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm text-slate-600 mb-1">主题</label>
            <input
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder="简短描述工单主题"
            />
          </div>

          <div>
            <label className="block text-sm text-slate-600 mb-1">详情</label>
            <textarea
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
              rows={4}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="详细描述需要处理的内容"
            />
          </div>

          {ticketType === "cross_department" ? (
            <div>
              <label className="block text-sm text-slate-600 mb-1">需要协助的部门</label>
              <select
                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
                value={requestedDeptId}
                onChange={(e) => setRequestedDeptId(e.target.value)}
              >
                <option value="">请选择部门</option>
                {crossDepartments.map((d) => (
                  <option key={d.id} value={d.id}>{d.name}</option>
                ))}
              </select>
            </div>
          ) : (
            <div>
              <label className="block text-sm text-slate-600 mb-1">处理人（可选，不选则交给管理员）</label>
              <select
                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
                value={targetUserId}
                onChange={(e) => setTargetUserId(e.target.value)}
              >
                <option value="">管理员</option>
                {participants.map((p) => (
                  <option key={p.id} value={p.id}>{p.username} {p.department_name ? `(${p.department_name})` : ""}</option>
                ))}
              </select>
            </div>
          )}

          {error && <p className="text-sm text-red-600">{error}</p>}
        </div>

        <div className="mt-6 flex justify-end gap-3">
          <button
            onClick={onClose}
            disabled={saving}
            className="rounded-md border border-slate-300 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-50"
          >
            取消
          </button>
          <button
            onClick={confirm}
            disabled={!canSubmit || saving}
            className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
          >
            {saving ? "提交中..." : "确认提交"}
          </button>
        </div>
      </div>
    </div>
  );
}
