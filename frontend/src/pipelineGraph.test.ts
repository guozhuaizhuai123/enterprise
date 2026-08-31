function assertEqual(actual: unknown, expected: unknown): void {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(`Expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}

const modulePath = "./pipelineGraph.ts";
const pipelineGraph = await import(modulePath).catch(() => null);
const buildPipelineGraph = pipelineGraph?.buildPipelineGraph;

const runningState = {
  sensitive_gate: { status: "done" },
  retrieval: { status: "running" },
  answer: { status: "idle" },
  faithfulness_check: { status: "idle" },
};

const runningGraph = buildPipelineGraph?.(runningState);
const retrievalNode = runningGraph?.nodes.find((node: { id: string }) => node.id === "retrieval");
const knowledgeIndexNode = runningGraph?.nodes.find((node: { id: string }) => node.id === "knowledge_index");
const knowledgeIndexEdge = runningGraph?.edges.find(
  (edge: { id: string }) => edge.id === "knowledge_index-retrieval",
);

assertEqual(retrievalNode?.data.label, "知识库检索");

assertEqual(knowledgeIndexNode?.data, {
  label: "部门知识索引",
  status: "running",
  detail: "正在查询授权部门索引",
});
assertEqual(
  knowledgeIndexEdge && {
    source: knowledgeIndexEdge.source,
    target: knowledgeIndexEdge.target,
    animated: knowledgeIndexEdge.animated,
    stroke: knowledgeIndexEdge.style?.stroke,
  },
  {
    source: "knowledge_index",
    target: "retrieval",
    animated: true,
    stroke: "#6366f1",
  },
);

const completedGraph = buildPipelineGraph?.({
  ...runningState,
  retrieval: { status: "done", detail: "命中 4 个片段" },
});
const completedIndexNode = completedGraph?.nodes.find((node: { id: string }) => node.id === "knowledge_index");
const completedIndexEdge = completedGraph?.edges.find(
  (edge: { id: string }) => edge.id === "knowledge_index-retrieval",
);

assertEqual(completedIndexNode?.data, {
  label: "部门知识索引",
  status: "done",
  detail: "命中 4 个片段",
});
assertEqual(completedIndexEdge?.animated, false);
assertEqual(completedIndexEdge?.style?.stroke, "#22c55e");
