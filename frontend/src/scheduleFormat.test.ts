import {
  formatLeaveRange,
  formatWeeklySchedule,
  shouldPreviewLeave,
} from "./scheduleFormat.ts";

function assertEqual(actual: unknown, expected: unknown): void {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(`Expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
  }
}

const defaultDays = Array.from({ length: 7 }, (_, index) => ({
  weekday: index + 1,
  enabled: index < 5,
  start_time: "09:00",
  end_time: "18:00",
}));

const customDays = Array.from({ length: 7 }, (_, index) => ({
  weekday: index + 1,
  enabled: index === 0 || index === 2,
  start_time: "08:30",
  end_time: "17:30",
}));

assertEqual(formatWeeklySchedule(defaultDays), "周一至周五 09:00–18:00");
assertEqual(formatWeeklySchedule(customDays), "周一、周三 08:30–17:30");
assertEqual(shouldPreviewLeave("我明天请病假"), true);
assertEqual(shouldPreviewLeave("我想请9月1日至3日年假"), true);
assertEqual(shouldPreviewLeave("周五弟弟结婚帮我请个假"), true);
assertEqual(shouldPreviewLeave("公司的病假制度是什么"), false);
assertEqual(shouldPreviewLeave("请假制度是什么"), false);
assertEqual(formatLeaveRange("2026-09-01", "2026-09-03"), "2026/9/1–2026/9/3");

console.log("scheduleFormat tests passed");
