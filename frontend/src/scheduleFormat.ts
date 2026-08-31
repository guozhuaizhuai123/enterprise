import type { ScheduleDay } from "./types";

export const LEAVE_TYPES = ["年假", "病假", "事假", "调休", "婚假", "产假", "陪产假", "丧假", "其他"];
export const WEEKDAY_LABELS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];

export function formatWeeklySchedule(days: ScheduleDay[]): string {
  const enabled = [...days].filter((day) => day.enabled).sort((a, b) => a.weekday - b.weekday);
  if (enabled.length === 0) return "未设置上班时间";

  const sameTime = enabled.every(
    (day) => day.start_time === enabled[0].start_time && day.end_time === enabled[0].end_time,
  );
  if (!sameTime) {
    return enabled
      .map(
        (day) =>
          `${WEEKDAY_LABELS[day.weekday - 1]} ${day.start_time}–${day.end_time}`,
      )
      .join("；");
  }

  const consecutive = enabled.every(
    (day, index) => index === 0 || day.weekday === enabled[index - 1].weekday + 1,
  );
  const labels = consecutive && enabled.length > 1
    ? `${WEEKDAY_LABELS[enabled[0].weekday - 1]}至${WEEKDAY_LABELS[enabled[enabled.length - 1].weekday - 1]}`
    : enabled.map((day) => WEEKDAY_LABELS[day.weekday - 1]).join("、");
  return `${labels} ${enabled[0].start_time}–${enabled[0].end_time}`;
}

export function shouldPreviewLeave(text: string): boolean {
  const policyQuestion = /制度|规定|政策|流程|怎么|如何|多久|多少|是否|最长|最少|销假/.test(text);
  const directRequest = /(?:帮我|替我|给我|我要|我想|我需要).{0,30}请(?:个|一下)?假/.test(text)
    || /(?:申请|请)(?:个|一下)?(?:年假|病假|事假|调休|婚假|产假|陪产假|丧假)/.test(text)
    || /(?:我要|我想|我需要).{0,30}(?:年假|病假|事假|调休|婚假|产假|陪产假|丧假)/.test(text);
  return directRequest || (/请(?:个|一下)?假/.test(text) && !policyQuestion);
}

function displayDate(value: string): string {
  const [year, month, day] = value.split("-").map(Number);
  return `${year}/${month}/${day}`;
}

export function formatLeaveRange(startDate: string, endDate: string): string {
  const start = displayDate(startDate);
  const end = displayDate(endDate);
  return start === end ? start : `${start}–${end}`;
}
