import Link from "next/link";
import type { ReactNode } from "react";
import { companies } from "@/lib/api";
import { monthLabel } from "@/lib/format";
import { CompanyTabs } from "@/components/CompanyTabs";

const TAB_PATH: Record<string, string> = {
  Overview: "", Cash: "/cash", Receivables: "/receivables", Integrity: "/integrity", Review: "/review",
};

export const clean = (name: string) => name.replace(" (made-up)", "");

/** The frame every company page shares: the company rail, the company name and the page tabs. */
export async function CompanyShell({ code, period, tab, children }: {
  code: string; period: string; tab: keyof typeof TAB_PATH; children: ReactNode;
}) {
  const list = await companies();
  const company = list.find((c) => c.code === code);
  return (
    <div className="shell">
      <nav className="rail" aria-label="Companies">
        {list.map((c) => (
          <Link key={c.code} href={`/company/${c.code}${TAB_PATH[tab]}?period=${period}`}
                aria-current={c.code === code ? "page" : undefined}>
            <span className="code">{c.code}</span> {clean(c.name)}
          </Link>
        ))}
      </nav>
      <main>
        <p className="note">Example Holding, made-up data · {monthLabel(period)}</p>
        <h1 className="verdict">{company ? clean(company.name) : code}</h1>
        <CompanyTabs code={code} period={period} current={tab} />
        {children}
      </main>
    </div>
  );
}
