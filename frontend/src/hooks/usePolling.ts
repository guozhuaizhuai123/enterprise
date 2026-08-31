import { useCallback, useEffect, useRef, useState } from "react";

/** 可选的自动刷新间隔（毫秒）。 */
export const POLL_INTERVALS = [5_000, 10_000, 20_000, 30_000] as const;

export type PollInterval = (typeof POLL_INTERVALS)[number];

export const DEFAULT_POLL_INTERVAL: PollInterval = 10_000;

const STORAGE_KEY = "eirs_auto_refresh_interval";

/** 读取用户上次选择的自动刷新间隔，非法值回落到默认值。 */
export function loadPollInterval(): PollInterval {
  const raw = Number(localStorage.getItem(STORAGE_KEY));
  return (POLL_INTERVALS as readonly number[]).includes(raw)
    ? (raw as PollInterval)
    : DEFAULT_POLL_INTERVAL;
}

export function savePollInterval(interval: PollInterval): void {
  localStorage.setItem(STORAGE_KEY, String(interval));
}

export function formatPollInterval(interval: number): string {
  return `${Math.round(interval / 1000)} 秒`;
}

export interface UsePollingOptions {
  /** 轮询间隔，传 0 或负值时停止自动刷新。 */
  interval: number;
  /** 轮询总开关。 */
  enabled?: boolean;
  /** 临时暂停：表单填写中、审批提交中等，避免把用户输入覆盖掉。 */
  paused?: boolean;
}

export interface UsePollingResult {
  /** 立即执行一次（手动刷新按钮、操作后强制同步）。 */
  refreshNow: () => Promise<void>;
  /** 最近一次成功刷新的时间戳，用于展示“已更新于”。 */
  lastRefreshedAt: number | null;
}

/**
 * 定时轮询。相比裸 `setInterval`，这里额外处理了三件容易踩的事：
 * 1. 用 ref 持有回调，页面每次重渲染不会重建定时器；
 * 2. 上一次请求还没回来时不重复发起，避免慢接口堆积出竞态；
 * 3. 标签页切到后台（document.hidden）时跳过拉取，回到前台立刻补一次。
 */
export function usePolling(
  callback: () => void | Promise<void>,
  { interval, enabled = true, paused = false }: UsePollingOptions,
): UsePollingResult {
  const callbackRef = useRef(callback);
  const inFlight = useRef(false);
  const [lastRefreshedAt, setLastRefreshedAt] = useState<number | null>(null);

  useEffect(() => {
    callbackRef.current = callback;
  }, [callback]);

  const run = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    try {
      await callbackRef.current();
      setLastRefreshedAt(Date.now());
    } catch {
      // 轮询失败不外抛：调用方通常是 `void run()`，抛出去只会变成
      // unhandled rejection。需要给用户提示时，应在 callback 内部处理。
    } finally {
      inFlight.current = false;
    }
  }, []);

  const active = enabled && !paused && interval > 0;

  useEffect(() => {
    if (!active) return;
    const id = window.setInterval(() => {
      if (!document.hidden) void run();
    }, interval);
    const onVisibilityChange = () => {
      if (!document.hidden) void run();
    };
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [active, interval, run]);

  return { refreshNow: run, lastRefreshedAt };
}
