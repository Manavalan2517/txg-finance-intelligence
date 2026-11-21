import Link from "next/link";
import { Banner } from "@astryxdesign/core/Banner";
import { CompanyShell } from "@/components/CompanyShell";
import { StatusLine } from "@/components/Status";
import { SeriesChart } from "@/components/lazy-charts";
import { ApiRefusal, kpis, periodFrom, receivables, series } from "@/lib/api";
import { formatValue, pct, sar } from "@/lib/format";

// Receivables (§11.2.5, §12.10–§12.11): ageing, days late against the customer's own normal, concentration.
const MEASURES = ["RC-1", "RC-1_days_late", "RC-2", "RC-3", "RC-5_top1", "RC-5"];

export default async function ReceivablesPage({ params, searchParams }: {
  params: Promise<{ code: string }>; searchParams: Promise<{ period?: string }>;
}) {
  const { code } = await params;
  const period = periodFrom((await searchParams).period);
  try {
    const [r, values, late] = await Promise.all([receivables(code, period), kpis(code, period),
                                                 series(code, "RC-1_days_late", period)]);
    const byId = new Map(values.map((k) => [k.kpi_id, k]));
    const total = r.ageing.reduce((s, b) => s + Number(b.sar), 0) || 1;
    const top = r.customers[0];
    return (
      <CompanyShell code={code} period={period} tab="Receivables">
        {top && top.share >= 0.3 && (
          <Banner status="warning" title={`${top.name} is ${pct(top.share, 0)} of the last 12 months' sales`}
                  description="One customer this large is a concentration risk: a late payment or a lost contract moves the whole company." />
        )}
        <section className="facts" aria-label="Receivable measures">
          {MEASURES.filter((id) => byId.has(id)).map((id) => {
            const k = byId.get(id)!;
            return (
              <div key={id}>
                <Link className="fact" href={`/company/${code}?period=${period}&kpi=${id}`}>{formatValue(k)}</Link>
                <span className="note">{k.name}</span><StatusLine k={k} />
              </div>
            );
          })}
        </section>
        <h2 className="section">Days late, last {late.months.length} months</h2>
        <SeriesChart months={late.months} values={late.values} lower={late.lower} upper={late.upper}
                     unit={late.unit} name={late.name} />
        <div className="two">
          <table className="others">
            <caption className="note" style={{ textAlign: "start" }}>Open invoices by days past due · retention held
              under contract counts as not yet due ({sar(Number(r.retention_held))})</caption>
            <thead><tr><th scope="col">Days past due</th><th scope="col" className="num">Open</th><th scope="col" className="num">Share</th></tr></thead>
            <tbody>{r.ageing.map((b) => (
              <tr key={b.bucket}><th scope="row">{b.bucket}</th><td className="num">{sar(Number(b.sar))}</td>
                <td className="num"><span className="bar" style={{ inlineSize: `${(Number(b.sar) / total) * 4}rem` }} aria-hidden />
                  {pct(Number(b.sar) / total, 0)}</td></tr>
            ))}</tbody>
          </table>
          <table className="others">
            <caption className="note" style={{ textAlign: "start" }}>Largest customers, last 12 months&rsquo; sales</caption>
            <thead><tr><th scope="col">Customer</th><th scope="col" className="num">Sales</th><th scope="col" className="num">Share</th></tr></thead>
            <tbody>{r.customers.map((c) => (
              <tr key={c.customer_id}><th scope="row">{c.name}</th><td className="num">{sar(Number(c.sales_sar))}</td>
                <td className="num">{pct(c.share, 0)}</td></tr>
            ))}</tbody>
          </table>
        </div>
      </CompanyShell>
    );
  } catch (e) {
    if (!(e instanceof ApiRefusal)) throw e;
    return (
      <CompanyShell code={code} period={period} tab="Receivables">
        <Banner status="warning" title="Receivables are not shown for this month"
                description={e.held ? `The month is on hold: ${e.held.reason}.` : String(e.detail)} />
      </CompanyShell>
    );
  }
}
