import { splitSSEBlocks } from "./sse.ts";

function assertEqual(actual: unknown, expected: unknown): void {
  if (actual !== expected) throw new Error(`Expected ${String(expected)}, got ${String(actual)}`);
}

function assertDeepEqual(actual: unknown, expected: unknown): void {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(`Expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}

const crlfEvent = 'event: message\r\ndata: {"node":"final","status":"completed"}\r\n\r\n';
const parsed = splitSSEBlocks(crlfEvent, true);

assertDeepEqual(parsed.blocks, [
  'event: message\ndata: {"node":"final","status":"completed"}',
]);
assertEqual(parsed.remainder, "");

const unterminated = splitSSEBlocks('data: {"node":"answer","status":"streaming","delta":"完成"}', true);
assertDeepEqual(unterminated.blocks, [
  'data: {"node":"answer","status":"streaming","delta":"完成"}',
]);
