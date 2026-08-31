import type { ThreadItem } from "./types";

interface ThreadDeletionState {
  threads: ThreadItem[];
  currentThreadDeleted: boolean;
}

export function getThreadStateAfterDeletion(
  threads: ThreadItem[],
  currentThreadId: string | null,
  deletedThreadId: string,
): ThreadDeletionState {
  return {
    threads: threads.filter((thread) => thread.id !== deletedThreadId),
    currentThreadDeleted: currentThreadId === deletedThreadId,
  };
}
