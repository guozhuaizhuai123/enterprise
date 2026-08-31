import type { DocumentItem, DocumentScopeMode, MemoryLevel } from "./types";

export const DEFAULT_MEMORY_LEVEL: MemoryLevel = 3;

const MEMORY_LEVEL_LABELS: Record<MemoryLevel, string> = {
  1: "极速",
  2: "较快",
  3: "均衡",
  4: "深入",
  5: "最深",
};

export function memoryLevelLabel(level: MemoryLevel): string {
  return MEMORY_LEVEL_LABELS[level];
}

export function scopeButtonLabel(mode: DocumentScopeMode, selectedIds: string[]): string {
  return mode === "all" ? "文档范围 · 全部" : `文档范围 · 已选 ${selectedIds.length} 份`;
}

export function toggleDocumentId(selectedIds: string[], id: string): string[] {
  return selectedIds.includes(id)
    ? selectedIds.filter((selectedId) => selectedId !== id)
    : [...selectedIds, id];
}

export function setDepartmentSelected(
  selectedIds: string[],
  departmentDocumentIds: string[],
  selected: boolean,
): string[] {
  if (!selected) {
    const departmentIds = new Set(departmentDocumentIds);
    return selectedIds.filter((id) => !departmentIds.has(id));
  }

  const currentIds = new Set(selectedIds);
  return [
    ...selectedIds,
    ...departmentDocumentIds.filter((id) => !currentIds.has(id)),
  ];
}

export function groupDocumentsByDepartment(
  documents: DocumentItem[],
  departmentLabels: Record<string, string>,
): Record<string, DocumentItem[]> {
  return documents.reduce<Record<string, DocumentItem[]>>((groups, document) => {
    const label = departmentLabels[document.department_id] ?? document.department_id;
    (groups[label] ??= []).push(document);
    return groups;
  }, {});
}
