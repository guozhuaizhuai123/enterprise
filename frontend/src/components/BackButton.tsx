import { useNavigate } from "react-router-dom";

export interface BackButtonProps {
  /** 没有应用内历史可回退时跳转的兜底路径。 */
  fallback?: string;
  label?: string;
}

/**
 * 应用内返回按钮。
 *
 * react-router 会在 history state 里维护 idx，idx > 0 说明本次会话里
 * 还有上一个应用内页面可以回退；否则跳到兜底页，避免退出到浏览器之外。
 */
export default function BackButton({ fallback = "/", label = "返回" }: BackButtonProps) {
  const navigate = useNavigate();
  const idx = (window.history.state as { idx?: number } | null)?.idx ?? 0;
  const canGoBack = idx > 0;

  function goBack() {
    if (canGoBack) navigate(-1);
    else navigate(fallback, { replace: true });
  }

  return (
    <button
      onClick={goBack}
      title={canGoBack ? "返回上一页" : `返回${label}页`}
      aria-label="返回"
      className="flex items-center gap-1 rounded border border-slate-200 px-2.5 py-1 text-sm text-slate-600 hover:bg-slate-50"
    >
      <span aria-hidden="true">←</span>
      {label}
    </button>
  );
}
