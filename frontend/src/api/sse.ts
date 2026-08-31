export interface SSEBlocks {
  blocks: string[];
  remainder: string;
}

/** Split complete SSE records while retaining an incomplete record for the next chunk. */
export function splitSSEBlocks(buffer: string, flush = false): SSEBlocks {
  const normalized = buffer.replace(/\r\n?/g, "\n");
  const parts = normalized.split("\n\n");
  const remainder = flush ? "" : (parts.pop() ?? "");
  return {
    blocks: parts.filter(Boolean),
    remainder,
  };
}
