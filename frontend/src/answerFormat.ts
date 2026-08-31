export type AnswerBlock =
  | { kind: "heading"; text: string }
  | { kind: "list-item"; marker: string; text: string }
  | { kind: "paragraph"; text: string };

const HEADING_LABELS = ["结论", "办理要点", "操作步骤", "依据", "信息不足", "注意事项", "风险提示"];

export function stripInternalReasoning(text: string): string {
  let cleaned = text
    .replace(/<think\b[^>]*>[\s\S]*?<\/think\s*>/gi, "")
    .replace(/<think\b[^>]*>[\s\S]*$/gi, "")
    .replace(/<\/?think\b[^>]*>/gi, "");

  const possibleTagStart = cleaned.lastIndexOf("<");
  if (possibleTagStart >= 0) {
    const tail = cleaned.slice(possibleTagStart).toLowerCase();
    if ("<think>".startsWith(tail)) cleaned = cleaned.slice(0, possibleTagStart);
  }
  return cleaned;
}

function cleanInline(text: string): string {
  return text
    .replace(/^#{1,6}\s*/, "")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/__([^_]+)__/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/^(当然可以|好的|没问题)[，,。.!！：:\s]*/, "")
    .replace(/[ \t]+/g, " ")
    .trim();
}

export function formatAnswerBlocks(text: string): AnswerBlock[] {
  const blocks: AnswerBlock[] = [];
  let bulletNumber = 0;

  for (const sourceLine of stripInternalReasoning(text).replace(/\r\n?/g, "\n").split("\n")) {
    const trimmed = sourceLine.trim();
    if (!trimmed || /^```/.test(trimmed) || /^[-*_]{3,}$/.test(trimmed)) continue;

    const numbered = trimmed.match(/^(\d+)[.)、]\s*(.+)$/);
    if (numbered) {
      blocks.push({ kind: "list-item", marker: numbered[1], text: cleanInline(numbered[2]) });
      bulletNumber = Number(numbered[1]);
      continue;
    }

    const bullet = trimmed.match(/^[-*•]\s+(.+)$/);
    if (bullet) {
      bulletNumber += 1;
      blocks.push({ kind: "list-item", marker: String(bulletNumber), text: cleanInline(bullet[1]) });
      continue;
    }

    const cleaned = cleanInline(trimmed);
    if (!cleaned) continue;

    const exactHeading = cleaned.replace(/[：:]$/, "");
    if (HEADING_LABELS.includes(exactHeading)) {
      blocks.push({ kind: "heading", text: exactHeading });
      bulletNumber = 0;
      continue;
    }

    const headingWithBody = HEADING_LABELS.find((label) => cleaned.startsWith(`${label}：`));
    if (headingWithBody) {
      blocks.push({ kind: "heading", text: headingWithBody });
      const body = cleaned.slice(headingWithBody.length + 1).trim();
      if (body) blocks.push({ kind: "paragraph", text: body });
      bulletNumber = 0;
      continue;
    }

    blocks.push({ kind: "paragraph", text: cleaned });
    bulletNumber = 0;
  }

  return blocks;
}
