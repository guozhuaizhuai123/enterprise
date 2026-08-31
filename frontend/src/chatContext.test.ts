import {
  memoryLevelLabel,
  scopeButtonLabel,
  setDepartmentSelected,
  toggleDocumentId,
  groupDocumentsByDepartment,
} from "./chatContext.ts";

function assertEqual(actual: unknown, expected: unknown): void {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(`Expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}

assertEqual(memoryLevelLabel(1), "极速");
assertEqual(memoryLevelLabel(2), "较快");
assertEqual(memoryLevelLabel(3), "均衡");
assertEqual(memoryLevelLabel(4), "深入");
assertEqual(memoryLevelLabel(5), "最深");
assertEqual(scopeButtonLabel("all", []), "文档范围 · 全部");
assertEqual(scopeButtonLabel("selected", ["doc-1", "doc-2"]), "文档范围 · 已选 2 份");
assertEqual(toggleDocumentId(["doc-1"], "doc-2"), ["doc-1", "doc-2"]);
assertEqual(toggleDocumentId(["doc-1", "doc-2"], "doc-1"), ["doc-2"]);
assertEqual(
  setDepartmentSelected(["hr-1", "legal-1"], ["legal-1", "legal-2"], true),
  ["hr-1", "legal-1", "legal-2"],
);
assertEqual(
  setDepartmentSelected(["hr-1", "legal-1", "legal-2"], ["legal-1", "legal-2"], false),
  ["hr-1"],
);
assertEqual(
  groupDocumentsByDepartment(
    [
      { id: "a", department_id: "legal", title: "A" },
      { id: "b", department_id: "hr", title: "B" },
      { id: "c", department_id: "legal", title: "C" },
    ] as never,
    { legal: "法务部", hr: "人事部" },
  ),
  {
    法务部: [
      { id: "a", department_id: "legal", title: "A" },
      { id: "c", department_id: "legal", title: "C" },
    ],
    人事部: [{ id: "b", department_id: "hr", title: "B" }],
  },
);

console.log("chatContext tests passed");
