import { NOTIFICATIONS_CLEARED_EVENT, notifyNotificationsCleared } from "./notificationEvents.ts";

function assertEqual(actual: unknown, expected: unknown): void {
  if (actual !== expected) throw new Error(`Expected ${String(expected)}, got ${String(actual)}`);
}

const target = new EventTarget();
let received = 0;
target.addEventListener(NOTIFICATIONS_CLEARED_EVENT, () => { received += 1; });

notifyNotificationsCleared(target);

assertEqual(received, 1);
