import type { Edge, Node } from "@xyflow/react";
import type { NodeKey, NodeStatus } from "./types/index.ts";

export interface PipelineNodeState {
  status: NodeStatus;
  detail?: string;
}

export type PipelineState = Record<NodeKey, PipelineNodeState>;

export const initialPipelineState: PipelineState = {
  sensitive_gate: { status: "idle" },
  retrieval: { status: "idle" },
  answer: { status: "idle" },
  faithfulness_check: { status: "idle" },
};

const NODE_LABELS: Record<NodeKey, string> = {
  sensitive_gate: "敏感话题门禁",
  retrieval: "知识库检索",
  answer: "回答 Agent",
  faithfulness_check: "溯源核查 Agent",
};

const ORDER: NodeKey[] = ["sensitive_gate", "retrieval", "answer", "faithfulness_check"];

function edgeColor(status: NodeStatus): string {
  if (status === "running") return "#6366f1";
  if (status === "done") return "#22c55e";
  if (status === "blocked") return "#ef4444";
  return "#e2e8f0";
}

function knowledgeIndexDetail(state: PipelineNodeState): string {
  if (state.status === "running") return "正在查询授权部门索引";
  if (state.status === "done") return state.detail ?? "检索完成";
  if (state.status === "blocked") return state.detail ?? "未命中";
  return "按部门隔离";
}

export function buildPipelineGraph(state: PipelineState): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = ORDER.map((key, idx) => ({
    id: key,
    type: "pipeline",
    position: { x: 0, y: idx * 118 },
    data: {
      label: NODE_LABELS[key],
      status: state[key].status,
      detail: state[key].detail,
      acceptsKnowledgeIndex: key === "retrieval",
    },
    draggable: false,
  }));

  nodes.push({
    id: "knowledge_index",
    type: "knowledgeIndex",
    position: { x: 230, y: 132 },
    data: {
      label: "部门知识索引",
      status: state.retrieval.status,
      detail: knowledgeIndexDetail(state.retrieval),
    },
    draggable: false,
  });

  const edges: Edge[] = ORDER.slice(0, -1).map((key, idx) => {
    const next = ORDER[idx + 1];
    const isActive = state[key].status === "done";
    return {
      id: `${key}-${next}`,
      source: key,
      target: next,
      animated: isActive && state[next].status === "running",
      style: { stroke: isActive ? "#22c55e" : "#e2e8f0", strokeWidth: 1.5 },
    };
  });

  edges.push({
    id: "knowledge_index-retrieval",
    source: "knowledge_index",
    target: "retrieval",
    targetHandle: "knowledge-index",
    animated: state.retrieval.status === "running",
    style: { stroke: edgeColor(state.retrieval.status), strokeWidth: 1.8 },
  });

  return { nodes, edges };
}
