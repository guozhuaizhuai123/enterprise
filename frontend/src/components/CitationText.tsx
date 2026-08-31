import { useState } from "react";
import type { Citation } from "../types";

const TAG_RE = /\[\[(C\d+)\]\]/g;

export default function CitationText({ text, citations }: { text: string; citations: Citation[] }) {
  const [active, setActive] = useState<Citation | null>(null);
  const byTag = new Map(citations.map((c) => [c.tag, c]));

  const parts: (string | { tag: string })[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  TAG_RE.lastIndex = 0;
  while ((match = TAG_RE.exec(text)) !== null) {
    if (match.index > lastIndex) parts.push(text.slice(lastIndex, match.index));
    parts.push({ tag: match[1] });
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < text.length) parts.push(text.slice(lastIndex));

  return (
    <div className="relative">
      <p className="whitespace-pre-wrap leading-relaxed">
        {parts.map((part, idx) => {
          if (typeof part === "string") return <span key={idx}>{part}</span>;
          const citation = byTag.get(part.tag);
          if (!citation) return <span key={idx}>[[{part.tag}]]</span>;
          return (
            <button
              key={idx}
              onClick={() => setActive(active?.tag === citation.tag ? null : citation)}
              className="inline-flex items-center justify-center mx-0.5 px-1.5 h-5 rounded bg-indigo-100 text-indigo-600 text-xs font-medium hover:bg-indigo-200 align-middle"
            >
              {citation.tag}
            </button>
          );
        })}
      </p>
      {active && (
        <div className="mt-2 rounded-md border border-indigo-200 bg-indigo-50 p-3 text-sm">
          <div className="flex items-center justify-between mb-1">
            <span className="font-medium text-indigo-700">{active.title}</span>
            <button onClick={() => setActive(null)} className="text-xs text-slate-400 hover:text-slate-600">
              关闭
            </button>
          </div>
          <p className="text-slate-600 whitespace-pre-wrap">{active.snippet}</p>
        </div>
      )}
    </div>
  );
}
