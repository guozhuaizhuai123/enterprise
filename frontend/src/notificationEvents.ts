export const NOTIFICATIONS_CLEARED_EVENT = "eirs:notifications-cleared";

export function notifyNotificationsCleared(target: EventTarget = window): void {
  target.dispatchEvent(new Event(NOTIFICATIONS_CLEARED_EVENT));
}
