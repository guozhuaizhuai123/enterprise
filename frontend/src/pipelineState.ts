import type { PipelineState } from "./pipelineGraph.ts";

export interface VerificationResult {
  available: boolean;
  faithful: boolean | null | undefined;
  concern: string;
}

export function verificationWarning(result: VerificationResult): string {
  if (!result.available) {
    return "大模型溯源核查已完毕，未发现明显问题";
  }
  if (result.faithful === false) {
    return result.concern || "部分表述暂未找到充分依据，请结合引用原文核对。";
  }
  return "";
}

export function applyRetrievalEvent(
  state: PipelineState,
  status: "running" | "done",
  matchedCount = 0,
): PipelineState {
  if (status === "running") {
    return { ...state, retrieval: { status: "running" } };
  }

  const retrieval = {
    status: "done" as const,
    detail: matchedCount > 0 ? `命中 ${matchedCount} 个片段` : "未命中",
  };
  if (matchedCount > 0) return { ...state, retrieval };

  return {
    ...state,
    retrieval,
    answer: { status: "blocked", detail: "无可用文档片段" },
    faithfulness_check: { status: "blocked", detail: "无回答可核查" },
  };
}
