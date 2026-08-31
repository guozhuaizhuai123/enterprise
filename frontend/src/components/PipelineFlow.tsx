import { useMemo } from "react";
import {
  ReactFlow,
  Background,
  Handle,
  Position,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { NodeStatus } from "../types";
import {
  buildPipelineGraph,
  type PipelineState,
} from "../pipelineGraph";

export { initialPipelineState, type PipelineState } from "../pipelineGraph";

const STATUS_STYLE: Record<NodeStatus, { bg: string; border: string; text: string; badge: string }> = {
  idle: { bg: "#fff", border: "#e2e8f0", text: "#64748b", badge: "待触发" },
  running: { bg: "#eef2ff", border: "#6366f1", text: "#4338ca", badge: "运行中" },
  done: { bg: "#f0fdf4", border: "#22c55e", text: "#15803d", badge: "已完成" },
  blocked: { bg: "#fef2f2", border: "#ef4444", text: "#b91c1c", badge: "已拦截" },
};

function PipelineNode({ data }: NodeProps) {
  const status = data.status as NodeStatus;
  const label = data.label as string;
  const detail = data.detail as string | undefined;
  const acceptsKnowledgeIndex = data.acceptsKnowledgeIndex as boolean | undefined;
  const style = STATUS_STYLE[status];

  return (
    <div
      className="rounded-lg px-4 py-3 shadow-sm min-w-[180px]"
      style={{ background: style.bg, border: `1.5px solid ${style.border}` }}
    >
      <Handle type="target" position={Position.Top} style={{ background: style.border }} />
      {acceptsKnowledgeIndex && (
        <Handle
          id="knowledge-index"
          type="target"
          position={Position.Right}
          style={{ background: style.border }}
        />
      )}
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-medium" style={{ color: style.text }}>
          {label}
        </span>
        {status === "running" && (
          <span className="w-2 h-2 rounded-full bg-indigo-500 animate-pulse" />
        )}
      </div>
      <div className="text-xs mt-1" style={{ color: style.text }}>
        {style.badge}
      </div>
      {detail && <div className="text-xs text-slate-500 mt-1 line-clamp-2">{detail}</div>}
      <Handle type="source" position={Position.Bottom} style={{ background: style.border }} />
    </div>
  );
}

function KnowledgeIndexNode({ data }: NodeProps) {
  const status = data.status as NodeStatus;
  const style = STATUS_STYLE[status];

  return (
    <div className="relative w-[138px] pt-2 text-center">
      <div
        className={`relative rounded-[12px_12px_22px_22px] px-3 pb-3 pt-5 shadow-sm ${
          status === "running" ? "animate-pulse" : ""
        }`}
        style={{ background: style.bg, border: `1.5px solid ${style.border}` }}
      >
        <div
          className="absolute -left-[1.5px] -right-[1.5px] -top-2 h-5 rounded-[50%]"
          style={{ background: style.bg, border: `1.5px solid ${style.border}` }}
        />
        <div className="relative text-xs font-semibold" style={{ color: style.text }}>
          {data.label as string}
        </div>
        <div className="relative mt-1 text-[10px] leading-4" style={{ color: style.text }}>
          {data.detail as string}
        </div>
        {status === "running" && (
          <span className="absolute right-2 top-3 h-2 w-2 rounded-full bg-indigo-500 animate-ping" />
        )}
        <Handle type="source" position={Position.Left} style={{ background: style.border }} />
      </div>
    </div>
  );
}

const nodeTypes = { pipeline: PipelineNode, knowledgeIndex: KnowledgeIndexNode };

export default function PipelineFlow({ state }: { state: PipelineState }) {
  const { nodes, edges } = useMemo(() => buildPipelineGraph(state), [state]);

  return (
    <div className="h-[520px] rounded-lg border border-slate-200 bg-slate-50">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        nodesConnectable={false}
        elementsSelectable={false}
        panOnDrag
        zoomOnScroll={false}
      >
        <Background color="#e2e8f0" gap={16} />
      </ReactFlow>
    </div>
  );
}
