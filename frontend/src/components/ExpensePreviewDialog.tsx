import { useEffect, useMemo, useState } from "react";
import type { ExpenseDraft, ExpensePreview } from "../types";

interface Props {
  open: boolean;
  preview: ExpensePreview | null;
  saving: boolean;
  error: string;
  onConfirm: (data: ExpenseDraft) => void;
  onClose: () => void;
}

export default function ExpensePreviewDialog({
  open,
  preview,
  saving,
  error,
  onConfirm,
  onClose,
}: Props) {
  const [title, setTitle] = useState("");
  const [purpose, setPurpose] = useState("");
  const [amount, setAmount] = useState("");
  const [category, setCategory] = useState("");
  const [expenseDate, setExpenseDate] = useState("");
  const [description, setDescription] = useState("");

  const today = useMemo(() => new Date().toISOString().slice(0, 10), []);

  useEffect(() => {
    if (!open || !preview) return;
    setTitle(preview.title ?? "");
    setPurpose(preview.purpose ?? "");
    setAmount(preview.total_amount ?? "");
    setCategory(preview.category ?? "其他");
    setExpenseDate(today);
    setDescription(preview.description ?? "");
  }, [open, preview, today]);

  if (!open || !preview) return null;

  const canSubmit =
    title.trim() &&
    amount.trim() &&
    !Number.isNaN(Number(amount)) &&
    Number(amount) > 0 &&
    category.trim() &&
    expenseDate;

  function confirm() {
    const data: ExpenseDraft = {
      title: title.trim(),
      purpose: purpose.trim() || description.trim(),
      project_code: "",
      currency: "CNY",
      total_amount: Number(amount).toFixed(2),
      items: [
        {
          expense_date: expenseDate,
          category: category.trim(),
          description: description.trim() || title.trim(),
          vendor: "",
          invoice_no: "",
          amount: Number(amount).toFixed(2),
          tax_amount: "0.00",
        },
      ],
    };
    onConfirm(data);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-lg rounded-xl bg-white p-6 shadow-lg">
        <h2 className="text-lg font-semibold text-slate-900">确认申请报销</h2>
        <p className="mt-1 text-sm text-slate-500">已从对话中提取信息，请核对后提交</p>

        <div className="mt-4 space-y-3">
          <div>
            <label className="block text-sm text-slate-600 mb-1">报销标题</label>
            <input
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="例如：六月出差交通费"
            />
          </div>

          <div>
            <label className="block text-sm text-slate-600 mb-1">用途说明</label>
            <input
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
              value={purpose}
              onChange={(e) => setPurpose(e.target.value)}
              placeholder="费用用途"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm text-slate-600 mb-1">金额（元）</label>
              <input
                type="number"
                step="0.01"
                min="0"
                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                placeholder="0.00"
              />
            </div>
            <div>
              <label className="block text-sm text-slate-600 mb-1">费用类别</label>
              <select
                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
              >
                <option value="">请选择</option>
                {["交通", "餐饮", "住宿", "办公", "通讯", "差旅", "其他"].map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label className="block text-sm text-slate-600 mb-1">费用日期</label>
            <input
              type="date"
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
              value={expenseDate}
              onChange={(e) => setExpenseDate(e.target.value)}
            />
          </div>

          <div>
            <label className="block text-sm text-slate-600 mb-1">费用说明</label>
            <textarea
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="补充说明"
            />
          </div>

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
