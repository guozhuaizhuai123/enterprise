import { getWorkScheduleCardView } from "./workScheduleCardState.ts";

function assertEqual<T>(actual: T, expected: T, message: string): void {
  if (actual !== expected) {
    throw new Error(`${message}: expected ${String(expected)}, got ${String(actual)}`);
  }
}

const expanded = getWorkScheduleCardView(false);
assertEqual(expanded.showDetails, true, "expanded card must show schedule details");
assertEqual(expanded.toggleLabel, "收起", "expanded card must offer collapse");

const collapsed = getWorkScheduleCardView(true);
assertEqual(collapsed.showDetails, false, "collapsed card must hide schedule details");
assertEqual(collapsed.toggleLabel, "展开", "collapsed card must offer expansion");

console.log("workScheduleCardState tests passed");
