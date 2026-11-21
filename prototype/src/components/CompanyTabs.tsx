import Link from "next/link";

const TABS = [
  ["", "Overview"],
  ["/cash", "Cash"],
  ["/receivables", "Receivables"],
  ["/integrity", "Integrity"],
  ["/review", "Review"],
] as const;

export function CompanyTabs({ code, period, current }: { code: string; period: string; current: string }) {
  return (
    <nav className="tabs" aria-label="Company pages">
      {TABS.map(([path, label]) => (
        <Link key={label} href={`/company/${code}${path}?period=${period}`}
              aria-current={current === label ? "page" : undefined}>{label}</Link>
      ))}
    </nav>
  );
}
