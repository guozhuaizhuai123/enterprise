import type { Citation } from "../types";
import { formatAnswerBlocks } from "../answerFormat";
import CitationText from "./CitationText";

export default function AnswerContent({ text, citations }: { text: string; citations: Citation[] }) {
  const blocks = formatAnswerBlocks(text);

  return (
    <div className="space-y-3">
      {blocks.map((block, index) => {
        if (block.kind === "heading") {
          return (
            <h3 key={`${block.kind}-${index}`} className="pt-1 text-[15px] font-semibold tracking-tight text-slate-900">
              {block.text}
            </h3>
          );
        }
        if (block.kind === "list-item") {
          return (
            <div key={`${block.kind}-${index}`} className="flex items-start gap-2.5">
              <span className="mt-0.5 flex h-5 min-w-5 items-center justify-center rounded-full bg-slate-100 px-1 text-[11px] font-semibold text-slate-600">
                {block.marker}
              </span>
              <div className="min-w-0 flex-1 text-slate-700">
                <CitationText text={block.text} citations={citations} />
              </div>
            </div>
          );
        }
        return (
          <div key={`${block.kind}-${index}`} className="text-slate-700">
            <CitationText text={block.text} citations={citations} />
          </div>
        );
      })}
    </div>
  );
}
