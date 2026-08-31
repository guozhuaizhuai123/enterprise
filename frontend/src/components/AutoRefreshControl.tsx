import { useEffect, useState } from "react";
import { formatPollInterval, POLL_INTERVALS } from "../hooks/usePolling";

const OFF = 0;

function relativeTime(at: number | null, now: number): string {
  if (!at) return "尚未更新";
  const seconds = Math.max(0, Math.round((now - at) / 1000));
  if (seconds < 5) return "刚刚更新";
  if (seconds < 60) return `${seconds} 秒前更新`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} 分钟前更新`;
  return `${Math.floor(minutes / 60)} 小时前更新`;
}

export interface AutoRefreshControlProps {
  /** 当前间隔，0 表示关闭自动刷新。 */
  interval: number;
  onIntervalChange: (interval: number) => void;
  lastRefreshedAt: number | null;
  busy?: boolean;
  onRefreshNow: () => void;
}

/**
 * 自动刷新开关 + 间隔选择 + 最近更新时间。
 * 选择会被记住，下次进入页面沿用同样节奏。
 */
export default function AutoRefreshControl({
  interval,
  onIntervalChange,
  lastRefreshedAt,
  busy = false,
  onRefreshNow,
}: AutoRefreshControlProps) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);

  const on = interval > 0;

  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="flex items-center gap-1.5 text-sm text-slate-500">
        <span
          className={`h-2 w-2 rounded-full ${on ? "animate-pulse bg-emerald-500" : "bg-slate-300"}`}
        />
        {on ? `每 ${formatPollInterval(interval)}自动刷新` : "自动刷新已关闭"}
      </span>
      <select
        aria-label="自动刷新间隔"
        value={interval}
        onChange={(event) => onIntervalChange(Number(event.target.value))}
        className="rounded-md border border-slate-300 px-2 py-1.5 text-sm text-slate-600 hover:bg-white"
      >
        {POLL_INTERVALS.map((value) => (
          <option key={value} value={value}>
            {formatPollInterval(value)}
          </option>
        ))}
        <option value={OFF}>关闭</option>
      </select>
      <span className="text-xs text-slate-400">{relativeTime(lastRefreshedAt, now)}</span>
      <button
        onClick={onRefreshNow}
        disabled={busy}
        className="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-white disabled:opacity-50"
      >
        立即刷新
      </button>
    </div>
  );
}
