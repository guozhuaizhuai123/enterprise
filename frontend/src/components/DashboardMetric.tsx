import { Link } from "react-router-dom";

interface DashboardMetricProps {
  label: string;
  value: string | number;
  detail?: string;
  tone?: "indigo" | "emerald" | "amber" | "slate";
  to?: string;
}

const tones = {
  indigo: "border-indigo-200 bg-indigo-50",
  emerald: "border-emerald-200 bg-emerald-50",
  amber: "border-amber-200 bg-amber-50",
  slate: "border-slate-200 bg-white",
};

export default function DashboardMetric({ label, value, detail, tone = "slate", to }: DashboardMetricProps) {
  const content = <><p className="text-sm text-slate-500">{label}</p><p className="mt-2 text-2xl font-semibold text-slate-900">{value}</p>{detail && <p className="mt-1 text-xs text-slate-400">{detail}</p>}</>;
  const className = `block rounded-xl border p-4 transition ${tones[tone]} ${to ? "cursor-pointer hover:-translate-y-0.5 hover:shadow-sm" : ""}`;
  return to ? <Link to={to} className={className}>{content}</Link> : <div className={className}>{content}</div>;
}
