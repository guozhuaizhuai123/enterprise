export interface WorkScheduleCardView {
  showDetails: boolean;
  toggleLabel: "收起" | "展开";
}

export function getWorkScheduleCardView(collapsed: boolean): WorkScheduleCardView {
  return collapsed
    ? { showDetails: false, toggleLabel: "展开" }
    : { showDetails: true, toggleLabel: "收起" };
}
