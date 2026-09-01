import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { askQuestion, cancelAssistantAction, confirmAssistantAction } from "../api/chat";
import AnswerContent from "../components/AnswerContent";
import AssistantActionCard from "../components/AssistantActionCard";
import AssistantResultCard from "../components/AssistantResultCard";
import { routeForKey } from "../assistantPresentation";
import {
  initialAdminAssistantState,
  reduceAdminAssistantEvent,
  startAdminAssistantAsk,
  type AdminAssistantState,
} from "../adminAssistantState";
import type { AssistantActionPreview, AssistantActionResult, PipelineEvent } from "../types";

const EXAMPLES = [
  "公司的请假制度是什么",
  "查询一下最近的项目",
  "查看今天考勤",
  "这个月支出怎么样",
  "查看工单",
];

export default function AdminAssistantPage() {
  const [state, setState] = useState<AdminAssistantState>(initialAdminAssistantState);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);
  const [actionResult, setActionResult] = useState<AssistantActionResult | null>(null);
  const [error, setError] = useState("");
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [state.messages]);

  // 企业全景的"向管理助手提问"链接会带上问题和部门筛选。只依赖查询参数：
  // ask 每次渲染都是新函数，放进依赖会让这个效果反复触发。
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    const prompt = searchParams.get("prompt");
    if (!prompt) return;
    const department = searchParams.get("department");
    setSearchParams(new URLSearchParams(), { replace: true });
    void ask(department ? `${prompt}（部门：${department}）` : prompt);
  }, [searchParams]);

  async function ask(question: string) {
    const trimmed = question.trim();
    if (!trimmed || busy) return;
    const now = Date.now();
    const assistantId = `assistant-${now}`;
    const currentThreadId = state.threadId;
    setBusy(true);
    setError("");
    setActionResult(null);
    setInput("");
    setState((current) => startAdminAssistantAsk(current, trimmed, `user-${now}`, assistantId));

    try {
      await askQuestion(trimmed, currentThreadId, (event: PipelineEvent) => {
        setState((current) => {
          const { state: next, effect } = reduceAdminAssistantEvent(current, event, "admin");
          if (effect.kind === "navigation") navigate(effect.href);
          return next;
        });
      });
    } catch {
      setError("请求失败，请稍后重试");
      setState((current) => ({
        ...current,
        messages: current.messages.map((message) =>
          message.id === assistantId ? { ...message, content: "请求失败，请稍后重试", streaming: false } : message,
        ),
      }));
    } finally {
      setBusy(false);
    }
  }

  async function confirm(action: AssistantActionPreview) {
    if (actionBusy) return;
    setActionBusy(true);
    setError("");
    try {
      const response = await confirmAssistantAction(
        action.action_id,
        action.confirmation_phrase || "确认执行",
        action.parameter_hash || "",
      );
      if ("status" in response) {
        const result = response as AssistantActionResult;
        setActionResult(result);
        if (result.status === "completed") setState((current) => ({ ...current, action: null }));
      } else {
        // 批量操作需要第二次确认：服务端返回新的预览与新的参数哈希
        setState((current) => ({ ...current, action: response as AssistantActionPreview }));
      }
    } catch {
      setError("操作执行失败，请重新发起");
    } finally {
      setActionBusy(false);
    }
  }

  async function cancel(action: AssistantActionPreview) {
    if (actionBusy) return;
    setActionBusy(true);
    try {
      setActionResult(await cancelAssistantAction(action.action_id));
      setState((current) => ({ ...current, action: null }));
    } catch {
      setError("操作取消失败，请稍后重试");
    } finally {
      setActionBusy(false);
    }
  }

  return (
    <div className="mx-auto flex h-full max-w-4xl flex-col gap-4">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">管理助手</h1>
        <p className="mt-1 text-sm text-slate-500">
          用一句话查询企业知识与实时数据、打开业务页面，或发起需要确认的管理操作。
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        {EXAMPLES.map((example) => (
          <button
            key={example}
            type="button"
            disabled={busy}
            onClick={() => void ask(example)}
            className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-slate-600 hover:border-indigo-300 hover:text-indigo-700 disabled:opacity-50"
          >
            {example}
          </button>
        ))}
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto rounded-xl border border-slate-200 bg-white p-4">
        {state.messages.length === 0 && (
          <p className="py-16 text-center text-sm text-slate-400">
            例如：“公司的请假制度是什么”“这个月支出怎么样”“查看工单”
          </p>
        )}
        {state.messages.map((message) => (
          <div key={message.id} className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-2xl rounded-lg px-4 py-3 text-sm ${
                message.role === "user"
                  ? "bg-indigo-600 text-white"
                  : "border border-slate-200 bg-slate-50 text-slate-800"
              }`}
            >
              {message.role === "assistant" ? (
                <>
                  <AnswerContent
                    text={message.content || (message.streaming ? "思考中..." : "")}
                    citations={message.citations ?? []}
                  />
                  {message.result && (
                    <AssistantResultCard
                      result={message.result}
                      href={routeForKey("admin", message.result.routeKey)}
                    />
                  )}
                </>
              ) : (
                <p className="whitespace-pre-wrap">{message.content}</p>
              )}
            </div>
          </div>
        ))}
        {state.action && (
          <AssistantActionCard
            action={state.action}
            busy={actionBusy}
            result={actionResult}
            onConfirm={() => void confirm(state.action!)}
            onCancel={() => void cancel(state.action!)}
          />
        )}
        {actionResult && state.action === null && (
          <div className="rounded-lg border border-slate-200 bg-white p-3 text-sm text-slate-700">
            操作结果：{actionResult.status}
            {actionResult.error_code ? `（${actionResult.error_code}）` : ""}
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div>
        <div className="min-h-5 px-1 pb-1 text-xs text-red-600" aria-live="polite">
          {error}
        </div>
        <div className="flex gap-2">
          <input
            className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
            value={input}
            placeholder="例如：查看今天考勤 / 这个月支出怎么样 / 创建组织部门：客户成功，编码:CS"
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void ask(input);
              }
            }}
            disabled={busy}
          />
          <button
            type="button"
            className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-60"
            onClick={() => void ask(input)}
            disabled={busy}
          >
            {busy ? "处理中..." : "发送"}
          </button>
        </div>
      </div>
    </div>
  );
}
