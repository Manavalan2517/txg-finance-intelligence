import Link from "next/link";
import { Banner } from "@astryxdesign/core/Banner";
import { StatusMark, TrendMark } from "@/components/Status";
import { clean } from "@/components/CompanyShell";
import { group, periodFrom, type GroupRow, type Kpi } from "@/lib/api";
import { formatValue, monthLabel } from "@/lib/format";

// The heat-grid (§16.3): every company, the four headline pairs (§11.1), status as colour + icon + word.
const PAIRS: [string, string[]][] = [
  ["Grow", ["HL-1_raw", "HL-2"]],
  ["Earn", ["HL-3", "HL-4_roic"]],
  ["Cash", ["HL-5", "HL-6"]],
  ["Survive", ["HL-7", "HL-8"]],
];
const IDS = PAIRS.flatMap(([, ids]) => ids);
const FILTERS = { all: "All companies", act: "Needs action", watch: "Watch or action" } as const;
const SORTS = { attention: "Most to act on", code: "Company code" } as const;
type Filter = keyof typeof FILTERS;
type Sort = keyof typeof SORTS;

const count = (row: GroupRow, s: string) => row.kpis.filter((k) => k.status === s).length;

function Cell({ k }: { k?: Kpi }) {
  if (!k) return <td className="cell cell-none"><span className="note">—</span></td>;
  return (
    <td className={`cell cell-${k.status}`}>
      <span className="cell-value">{formatValue(k)}</span>
      {k.state === "ok" && <span className="cell-mark"><StatusMark status={k.status} /> <TrendMark trend={k.trend} /></span>}
    </td>
  );
}

export default async function GroupPage({ searchParams }: {
  searchParams: Promise<{ period?: string; show?: string; sort?: string }>;
}) {
  const sp = await searchParams;
  const period = periodFrom(sp.period);
  const show: Filter = sp.show && sp.show in FILTERS ? (sp.show as Filter) : "all";
  const sort: Sort = sp.sort && sp.sort in SORTS ? (sp.sort as Sort) : "attention";
  const rows = await group(period);
  const names = new Map(rows.flatMap((r) => r.kpis).map((k) => [k.kpi_id, k.name]));
  const visible = rows
    .filter((r) => show === "all" || r.held || count(r, "act") > 0 || (show === "watch" && count(r, "watch") > 0))
    .sort((a, b) => sort === "code" ? a.code.localeCompare(b.code)
      : count(b, "act") - count(a, "act") || count(b, "watch") - count(a, "watch") || a.code.localeCompare(b.code));
  const acting = rows.filter((r) => count(r, "act") > 0).length;
  const href = (p: Partial<{ show: string; sort: string }>) =>
    `/?period=${period}&show=${p.show ?? show}&sort=${p.sort ?? sort}`;
  return (
    <main className="wide">
      <p className="note">Example Holding, made-up data · {monthLabel(period)}</p>
      <h1 className="verdict">{acting} of {rows.length} companies have a headline measure that needs action.</h1>
      <div className="controls" role="group" aria-label="Filter and sort">
        <span className="note">Show</span>
        {Object.entries(FILTERS).map(([key, label]) => (
          <Link key={key} className="chip" href={href({ show: key })} aria-current={show === key ? "true" : undefined}>{label}</Link>
        ))}
        <span className="note sep">Sort by</span>
        {Object.entries(SORTS).map(([key, label]) => (
          <Link key={key} className="chip" href={href({ sort: key })} aria-current={sort === key ? "true" : undefined}>{label}</Link>
        ))}
      </div>
      {visible.length === 0 && <Banner status="success" title="No company matches this filter." />}
      <div className="grid-scroll">
        <table className="heat">
          <caption className="visually-hidden">Headline measures by company for {monthLabel(period)}</caption>
          <thead>
            <tr>
              <th scope="col" rowSpan={2}>Company</th>
              {PAIRS.map(([label, ids]) => <th key={label} scope="colgroup" colSpan={ids.length} className="pair-head">{label}</th>)}
            </tr>
            <tr>{IDS.map((id) => <th key={id} scope="col" className="kpi-head">{names.get(id) ?? id}</th>)}</tr>
          </thead>
          <tbody>
            {visible.map((r) => {
              const byId = new Map(r.kpis.map((k) => [k.kpi_id, k]));
              return (
                <tr key={r.code}>
                  <th scope="row">
                    <Link href={`/company/${r.code}?period=${period}`}><span className="code">{r.code}</span> {clean(r.name)}</Link>
                  </th>
                  {r.held
                    ? <td colSpan={IDS.length} className="cell cell-held">On hold: {r.reason}. Nothing is shown until the trial balance ties.</td>
                    : IDS.map((id) => <Cell key={id} k={byId.get(id)} />)}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="note">Trends count only signals that pass the group-wide false-alarm limit (10%). Statuses for
        margins use each company&rsquo;s own normal range until peer bands exist.</p>
    </main>
  );
}
