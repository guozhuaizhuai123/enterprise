import { useEffect, useMemo, useState } from "react";
import { setDepartmentSelected, toggleDocumentId } from "../chatContext";
import type { DocumentItem, DocumentScopeMode, ThreadContextSettings } from "../types";

interface DocumentScopeDialogProps {
  open: boolean;
  documents: DocumentItem[];
  departmentLabels: Record<string, string>;
  value: ThreadContextSettings;
  saving: boolean;
  onApply: (next: ThreadContextSettings) => Promise<void>;
  onClose: () => void;
}

export default function DocumentScopeDialog({
  open,
  documents,
  departmentLabels,
  value,
  saving,
  onApply,
  onClose,
}: DocumentScopeDialogProps) {
  const [search, setSearch] = useState("");
  const [draftMode, setDraftMode] = useState<DocumentScopeMode>("all");
  const [draftIds, setDraftIds] = useState<string[]>([]);
  const [applyError, setApplyError] = useState("");

  useEffect(() => {
    if (!open) return;
    setSearch("");
    setDraftMode(value.document_scope_mode);
    setDraftIds(value.document_scope_mode === "all" ? [] : value.document_ids);
    setApplyError("");
  }, [open, value]);

  const documentsByDepartment = useMemo(() => {
    return documents.reduce<Record<string, DocumentItem[]>>((groups, document) => {
      (groups[document.department_id] ??= []).push(document);
      return groups;
    }, {});
  }, [documents]);

  const visibleGroups = useMemo(() => {
    const query = search.trim().toLocaleLowerCase();
    return Object.entries(documentsByDepartment)
      .map(([departmentId, departmentDocuments]) => ({
        departmentId,
        label: departmentLabels[departmentId] ?? departmentId,
        documents: query
          ? departmentDocuments.filter((document) =>
              [document.title, document.category, departmentLabels[departmentId] ?? departmentId]
                .join(" ")
                .toLocaleLowerCase()
                .includes(query),
            )
          : departmentDocuments,
      }))
      .filter((group) => group.documents.length > 0);
  }, [departmentLabels, documentsByDepartment, search]);

  const authorizedIds = useMemo(
    () => new Set(documents.map((document) => document.id)),
    [documents],
  );
  const effectiveDraftIds = draftMode === "all"
    ? documents.map((document) => document.id)
    : draftIds.filter((id) => authorizedIds.has(id));

  if (!open) return null;

  function chooseAllDocuments() {
    setDraftMode("all");
    setDraftIds([]);
    setApplyError("");
  }

  function clearSelection() {
    setDraftMode("selected");
    setDraftIds([]);
    setApplyError("");
  }

  function toggleOne(documentId: string) {
    setDraftMode("selected");
    setDraftIds(toggleDocumentId(effectiveDraftIds, documentId));
    setApplyError("");
  }

  function toggleDepartment(departmentId: string) {
    const departmentIds = documentsByDepartment[departmentId].map((document) => document.id);
    const allSelected = departmentIds.every((id) => effectiveDraftIds.includes(id));
    setDraftMode("selected");
    setDraftIds(setDepartmentSelected(effectiveDraftIds, departmentIds, !allSelected));
    setApplyError("");
  }

  async function applySelection() {
    if (draftMode === "selected" && effectiveDraftIds.length === 0) {
      setApplyError("请至少选择一份文档，或切换为全部文档");
      return;
    }
    setApplyError("");
    try {
      await onApply({
        memory_level: value.memory_level,
        document_scope_mode: draftMode,
        document_ids: draftMode === "all" ? [] : effectiveDraftIds,
      });
    } catch {
      setApplyError("文档范围保存失败，请稍后重试");
    }
  }

  const invalidSelection = draftMode === "selected" && effectiveDraftIds.length === 0;

  return (
    <div
      role="presentation"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !saving) onClose();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="document-scope-title"
        className="flex h-[min(680px,calc(100vh-2rem))] w-full max-w-2xl flex-col overflow-hidden rounded-lg bg-white shadow-xl"
      >
        <div className="border-b border-slate-200 px-5 py-4">
          <div className="flex items-center justify-between gap-4">
            <div>
              <h2 id="document-scope-title" className="text-base font-semibold text-slate-900">选择文档范围</h2>
              <p className="mt-1 text-xs text-slate-500">仅显示你当前有权读取的文档</p>
            </div>
            <button type="button" onClick={onClose} disabled={saving} aria-label="关闭文档范围" className="h-8 w-8 rounded text-slate-400 hover:bg-slate-100 hover:text-slate-700 disabled:opacity-50">×</button>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <input
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="搜索标题、分类或部门"
              aria-label="搜索文档"
              disabled={saving}
              className="min-w-48 flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:bg-slate-50"
            />
            <button type="button" onClick={chooseAllDocuments} disabled={saving} className={`rounded-md border px-3 py-2 text-sm ${draftMode === "all" ? "border-indigo-300 bg-indigo-50 text-indigo-700" : "border-slate-300 text-slate-600 hover:bg-slate-50"} disabled:opacity-50`}>全部文档</button>
            <button type="button" onClick={clearSelection} disabled={saving} className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-50">清空选择</button>
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-3">
          {visibleGroups.map((group) => {
            const allDepartmentIds = documentsByDepartment[group.departmentId].map((document) => document.id);
            const allSelected = allDepartmentIds.every((id) => effectiveDraftIds.includes(id));
            return (
              <section key={group.departmentId} className="border-b border-slate-100 py-3 last:border-0">
                <div className="mb-2 flex items-center justify-between gap-3">
                  <h3 className="text-sm font-medium text-slate-700">{group.label}</h3>
                  <button type="button" onClick={() => toggleDepartment(group.departmentId)} disabled={saving} className="text-xs text-indigo-600 hover:text-indigo-800 disabled:opacity-50">
                    {allSelected ? "取消全选" : "本部门全选"}
                  </button>
                </div>
                <div className="space-y-1">
                  {group.documents.map((document) => (
                    <label key={document.id} className="flex min-h-10 cursor-pointer items-center gap-3 rounded px-2 py-2 hover:bg-slate-50 has-[:disabled]:cursor-not-allowed">
                      <input
                        type="checkbox"
                        checked={effectiveDraftIds.includes(document.id)}
                        onChange={() => toggleOne(document.id)}
                        disabled={saving}
                        aria-label={`选择文档：${document.title}`}
                        className="h-4 w-4 shrink-0 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                      />
                      <span className="min-w-0 flex-1 truncate text-sm text-slate-700">{document.title}</span>
                      <span className="max-w-36 truncate text-xs text-slate-400">{document.category || "未分类"}</span>
                    </label>
                  ))}
                </div>
              </section>
            );
          })}
          {visibleGroups.length === 0 && (
            <p className="py-16 text-center text-sm text-slate-400">{documents.length === 0 ? "暂无可用文档" : "没有匹配的文档"}</p>
          )}
        </div>

        <div className="border-t border-slate-200 px-5 py-4">
          <div className="flex min-h-9 flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm text-slate-600">{draftMode === "all" ? `全部 ${documents.length} 份文档` : `已选 ${effectiveDraftIds.length} 份`}</p>
              {(invalidSelection || applyError) && <p role="alert" className="mt-1 text-xs text-red-600">{applyError || "请至少选择一份文档，或切换为全部文档"}</p>}
            </div>
            <div className="flex items-center gap-2">
              <button type="button" onClick={onClose} disabled={saving} className="rounded-md px-4 py-2 text-sm text-slate-600 hover:bg-slate-50 disabled:opacity-50">取消</button>
              <button type="button" onClick={() => void applySelection()} disabled={saving || invalidSelection} className="min-w-20 rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50">
                {saving ? "保存中..." : "应用"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
