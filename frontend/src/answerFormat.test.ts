import { formatAnswerBlocks } from "./answerFormat.ts";

function assertEqual(actual: unknown, expected: unknown): void {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(`Expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}

assertEqual(
  formatAnswerBlocks(`\`\`\`markdown
### **结论**

- **需要主管审批** [[C1]]
---
材料不足时，请联系人事部门。
\`\`\``),
  [
    { kind: "heading", text: "结论" },
    { kind: "list-item", marker: "1", text: "需要主管审批 [[C1]]" },
    { kind: "paragraph", text: "材料不足时，请联系人事部门。" },
  ],
);

assertEqual(
  formatAnswerBlocks("办理要点：\n1、准备申请材料\n2. 提交直属主管审批"),
  [
    { kind: "heading", text: "办理要点" },
    { kind: "list-item", marker: "1", text: "准备申请材料" },
    { kind: "list-item", marker: "2", text: "提交直属主管审批" },
  ],
);

assertEqual(
  formatAnswerBlocks("<think>Clarifying snippet duration and citation requirements</think>\n结论：可以办理。"),
  [
    { kind: "heading", text: "结论" },
    { kind: "paragraph", text: "可以办理。" },
  ],
);

assertEqual(
  formatAnswerBlocks("<think>Clarifying snippet duration"),
  [],
);

console.log("answerFormat tests passed");
