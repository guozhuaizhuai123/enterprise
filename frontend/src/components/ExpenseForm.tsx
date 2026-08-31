import { useState } from "react";
import { sumExpenseAmounts } from "../expenseFormat";
import type { ExpenseClaim, ExpenseDraft, ExpenseItem } from "../types";

interface ExpenseFormProps {
  initial?: ExpenseClaim | null;
  busy: boolean;
  onSave: (draft: ExpenseDraft, files: File[]) => Promise<void>;
  onCancel: () => void;
}

function blankItem(): ExpenseItem {
  return {
    expense_date: new Date().toISOString().slice(0, 10),
    category: "",
    description: "",
    vendor: "",
    invoice_no: "",
    amount: "",
    tax_amount: "0.00",
  };
}

export default function ExpenseForm({ initial, busy, onSave, onCancel }: ExpenseFormProps) {
  const [title, setTitle] = useState(initial?.title ?? "");
  const [purpose, setPurpose] = useState(initial?.purpose ?? "");
  const [projectCode, setProjectCode] = useState(initial?.project_code ?? "");
  const [items, setItems] = useState<ExpenseItem[]>(initial?.items.length ? initial.items : [blankItem()]);
  const [files, setFiles] = useState<File[]>([]);
  const [validation, setValidation] = useState("");
  const total = sumExpenseAmounts(items.map((item) => item.amount));

  function updateItem(index: number, patch: Partial<ExpenseItem>) {
    setItems((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!title.trim() || !total || items.some((item) => !item.category.trim() || !item.expense_date)) {
      setValidation("请填写报销主题、费用日期、类别和有效金额");
      return;
    }
    if (files.some((file) => file.size > 10 * 1024 * 1024)) {
      setValidation("单个附件不能超过 10 MB");
      return;
    }
    setValidation("");
    await onSave({
      title: title.trim(),
      purpose: purpose.trim(),
      project_code: projectCode.trim(),
      currency: "CNY",
      total_amount: total,
      items: items.map((item) => ({
        expense_date: item.expense_date,
        category: item.category.trim(),
        description: item.description.trim(),
        vendor: item.vendor.trim(),
        invoice_no: item.invoice_no.trim(),
        amount: Number(item.amount).toFixed(2),
        tax_amount: Number(item.tax_amount || 0).toFixed(2),
      })),
    }, files);
  }

  const inputClass = "w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-100";

  return (
    <form onSubmit={submit} className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="text-sm text-slate-600 sm:col-span-2">报销主题<input className={`${inputClass} mt-1`} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="如：8 月客户现场差旅费" /></label>
        <label className="text-sm text-slate-600">项目 / 成本编号<input className={`${inputClass} mt-1`} value={projectCode} onChange={(e) => setProjectCode(e.target.value)} placeholder="可选" /></label>
        <label className="text-sm text-slate-600">币种<input className={`${inputClass} mt-1 bg-slate-50`} value="CNY" disabled /></label>
        <label className="text-sm text-slate-600 sm:col-span-2">报销事由<textarea className={`${inputClass} mt-1 min-h-16`} value={purpose} onChange={(e) => setPurpose(e.target.value)} /></label>
      </div>

      <div>
        <div className="mb-2 flex items-center justify-between"><h3 className="text-sm font-semibold text-slate-800">费用明细</h3><button type="button" onClick={() => setItems((current) => [...current, blankItem()])} className="text-sm text-indigo-600">+ 添加一行</button></div>
        <div className="space-y-3">
          {items.map((item, index) => (
            <div key={index} className="rounded-lg border border-slate-200 bg-slate-50 p-3">
              <div className="grid gap-2 sm:grid-cols-4">
                <input type="date" className={inputClass} value={item.expense_date} onChange={(e) => updateItem(index, { expense_date: e.target.value })} />
                <input className={inputClass} placeholder="费用类别*" value={item.category} onChange={(e) => updateItem(index, { category: e.target.value })} />
                <input className={inputClass} placeholder="商户 / 供应商" value={item.vendor} onChange={(e) => updateItem(index, { vendor: e.target.value })} />
                <input className={inputClass} placeholder="发票号码" value={item.invoice_no} onChange={(e) => updateItem(index, { invoice_no: e.target.value })} />
                <input className={`${inputClass} sm:col-span-2`} placeholder="费用说明" value={item.description} onChange={(e) => updateItem(index, { description: e.target.value })} />
                <input inputMode="decimal" className={inputClass} placeholder="含税金额*" value={item.amount} onChange={(e) => updateItem(index, { amount: e.target.value })} />
                <div className="flex gap-2"><input inputMode="decimal" className={inputClass} placeholder="税额" value={item.tax_amount} onChange={(e) => updateItem(index, { tax_amount: e.target.value })} />{items.length > 1 && <button type="button" onClick={() => setItems((current) => current.filter((_, itemIndex) => itemIndex !== index))} className="text-xs text-red-500">删除</button>}</div>
              </div>
            </div>
          ))}
        </div>
        <div className="mt-3 text-right text-sm text-slate-500">合计：<strong className="text-lg text-slate-900">¥ {total ?? "—"}</strong></div>
      </div>

      <label className="block text-sm text-slate-600">票据附件（PDF / JPG / PNG / HEIC，单个不超过 10 MB）<input type="file" multiple accept=".pdf,.jpg,.jpeg,.png,.heic,.heif" className="mt-2 block w-full text-sm text-slate-500" onChange={(e) => setFiles(Array.from(e.target.files ?? []))} /></label>
      {initial?.attachments.length ? <p className="text-xs text-slate-400">已上传 {initial.attachments.length} 个附件；新选择的文件会追加上传。</p> : null}
      {validation && <p className="text-sm text-red-600">{validation}</p>}
      <div className="flex justify-end gap-3 border-t border-slate-100 pt-4"><button type="button" onClick={onCancel} className="px-4 py-2 text-sm text-slate-500">取消</button><button disabled={busy} className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">{busy ? "保存中..." : "保存草稿"}</button></div>
    </form>
  );
}
