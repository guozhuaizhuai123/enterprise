import { memoryLevelLabel, scopeButtonLabel } from "../chatContext";
import type { MemoryLevel, ThreadContextSettings } from "../types";

interface ChatContextToolbarProps {
  value: ThreadContextSettings;
  disabled: boolean;
  onMemoryLevelChange: (level: MemoryLevel) => void;
  onOpenDocumentScope: () => void;
}

const MEMORY_LEVELS: MemoryLevel[] = [1, 2, 3, 4, 5];

export default function ChatContextToolbar({
  value,
  disabled,
  onMemoryLevelChange,
  onOpenDocumentScope,
}: ChatContextToolbarProps) {
  return (
    <div className="flex min-h-14 flex-wrap items-center gap-x-5 gap-y-3 rounded-t-md border border-b-0 border-slate-300 bg-slate-50 px-3 py-2">
      <fieldset disabled={disabled} className="min-w-0 flex-1 sm:min-w-[360px]">
        <legend className="sr-only">上下文记忆深度</legend>
        <div className="flex items-center gap-3">
          <span className="w-16 shrink-0 text-right text-xs text-slate-500">响应更快</span>
          <div className="relative grid h-6 min-w-36 flex-1 grid-cols-5 items-center">
            <div aria-hidden="true" className="absolute left-[10%] right-[10%] top-1/2 h-1 -translate-y-1/2 rounded bg-slate-200" />
            {MEMORY_LEVELS.map((level) => (
              <label key={level} className="relative flex h-6 cursor-pointer items-center justify-center has-[:disabled]:cursor-not-allowed">
                <input
                  type="radio"
                  name="chat-memory-level"
                  value={level}
                  checked={value.memory_level === level}
                  onChange={() => onMemoryLevelChange(level)}
                  disabled={disabled}
                  aria-label={`${level} 档：${memoryLevelLabel(level)}`}
                  className="peer sr-only"
                />
                <span className="h-3.5 w-3.5 rounded-full border border-slate-300 bg-white shadow-sm transition peer-checked:border-indigo-600 peer-checked:bg-indigo-600 peer-focus-visible:ring-2 peer-focus-visible:ring-indigo-500 peer-focus-visible:ring-offset-2 peer-disabled:opacity-50" />
              </label>
            ))}
          </div>
          <span className="w-16 shrink-0 text-xs text-slate-500">上下文更深</span>
          <span className="w-9 shrink-0 text-center text-xs font-medium text-indigo-700" aria-live="polite">
            {memoryLevelLabel(value.memory_level)}
          </span>
        </div>
      </fieldset>

      <div className="flex shrink-0 items-center gap-2">
        <button
          type="button"
          onClick={onOpenDocumentScope}
          disabled={disabled}
          className="inline-flex min-h-9 min-w-36 items-center justify-center gap-2 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700 hover:border-indigo-300 hover:text-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <span aria-hidden="true" className="text-base leading-none">▤</span>
          {scopeButtonLabel(value.document_scope_mode, value.document_ids)}
        </button>
        <span className="hidden w-20 text-xs leading-4 text-slate-400 lg:block">限定本次会话检索</span>
      </div>
    </div>
  );
}
