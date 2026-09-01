import { Link } from "react-router-dom";
import type { AssistantResultPresentation } from "../assistantPresentation";

interface Props {
  result: AssistantResultPresentation;
  /** 已解析好的站内路径；解析不出可用路由时不传，卡片就不显示跳转按钮。 */
  href?: string | null;
}

export default function AssistantResultCard({ result, href }: Props) {
  return (
    <section className="mt-3 rounded-lg border border-indigo-100 bg-indigo-50 p-3 text-sm text-slate-700">
      <p className="font-semibold text-indigo-900">{result.title}</p>
      <ul className="mt-1 space-y-1">
        {result.lines.slice(0, 6).map((line, index) => <li key={`${index}-${line}`}>{line}</li>)}
      </ul>
      {href && (
        <Link to={href} className="mt-2 inline-flex text-xs font-medium text-indigo-700 hover:text-indigo-900">
          打开相关页面 →
        </Link>
      )}
    </section>
  );
}
