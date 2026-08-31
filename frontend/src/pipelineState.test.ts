function assertEqual(actual: unknown, expected: unknown): void {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(`Expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}

const initialState = {
  sensitive_gate: { status: "done" },
  retrieval: { status: "idle" },
  answer: { status: "idle" },
  faithfulness_check: { status: "idle" },
};

const modulePath = "./pipelineState.ts";
const pipelineState = await import(modulePath).catch(() => null);
const applyRetrievalEvent = pipelineState?.applyRetrievalEvent;
const verificationWarning = pipelineState?.verificationWarning;

assertEqual(applyRetrievalEvent?.(initialState, "running"), {
  ...initialState,
  retrieval: { status: "running" },
});

assertEqual(applyRetrievalEvent?.(initialState, "done", 4), {
  ...initialState,
  retrieval: { status: "done", detail: "命中 4 个片段" },
});

assertEqual(applyRetrievalEvent?.(initialState, "done", 0), {
  ...initialState,
  retrieval: { status: "done", detail: "未命中" },
  answer: { status: "blocked", detail: "无可用文档片段" },
  faithfulness_check: { status: "blocked", detail: "无回答可核查" },
});

assertEqual(
  verificationWarning?.({ available: false, faithful: null, concern: "溯源核查暂不可用，当前回答已保留。" }),
  "大模型溯源核查已完毕，未发现明显问题",
);
assertEqual(
  verificationWarning?.({ available: true, faithful: false, concern: "具体数字缺少引用依据。" }),
  "具体数字缺少引用依据。",
);
assertEqual(verificationWarning?.({ available: true, faithful: true, concern: "" }), "");
