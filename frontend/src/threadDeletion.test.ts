import type { ThreadItem } from "./types/index.ts";

function assertEqual(actual: unknown, expected: unknown): void {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(`Expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}

const threads: ThreadItem[] = [
  { id: "thread-1", title: "第一个会话", created_at: "2026-08-30T00:00:00Z" },
  { id: "thread-2", title: "第二个会话", created_at: "2026-08-30T00:01:00Z" },
];

const modulePath = "./threadDeletion.ts";
const threadDeletion = await import(modulePath).catch(() => null);
const getThreadStateAfterDeletion = threadDeletion?.getThreadStateAfterDeletion;

assertEqual(getThreadStateAfterDeletion?.(threads, "thread-1", "thread-1"), {
  threads: [threads[1]],
  currentThreadDeleted: true,
});

assertEqual(getThreadStateAfterDeletion?.(threads, "thread-1", "thread-2"), {
  threads: [threads[0]],
  currentThreadDeleted: false,
});
