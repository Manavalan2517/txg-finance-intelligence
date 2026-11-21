import { Banner } from "@astryxdesign/core/Banner";
import { CompanyShell } from "@/components/CompanyShell";
import { StatusMark } from "@/components/Status";
import { FanChart } from "@/components/lazy-charts";
import { ApiRefusal, cash13, periodFrom, type Cash13 } from "@/lib/api";
import { pct, sar } from "@/lib/format";

// The 13-week cash view (§12.8): every invoice, bill, salary run, loan payment and Zakat date, simulated 2,000 times.
function status(p: number): string {
  return p >= 0.2 ? "act" : p >= 0.05 ? "watch" : "healthy";
}

export default async function CashPage({ params, searchParams }: {
  params: Promise<{ code: string }>; searchParams: Promise<{ period?: string }>;
}) {
  const { code } = await params;
  const period = periodFrom((await searchParams).period);
  let f: Cash13 | null = null;
  let reason = "";
  try {
    f = await cash13(code, period);
  } catch (e) {
    if (!(e instanceof ApiRefusal)) throw e;
    reason = String(e.detail);
  }
  return (
    <CompanyShell code={code} period={period} tab="Cash">
      {!f ? <Banner status="info" title="No 13-week forecast for this month" description={reason} /> : (
        <>
          <section className="facts" aria-label="Thirteen-week cash">
            <div><span className="fact">{sar(f.low_point_p50)}</span><span className="note">Likely low point (median)</span></div>
            <div><span className="fact">{sar(f.low_point_p10)}</span><span className="note">1-in-10 bad case</span></div>
            <div><span className="fact">{pct(f.chance_below_minimum, 0)}</span>
              <span className="note">Chance of falling below {sar(f.minimum)}</span>
              <StatusMark status={status(f.chance_below_minimum)} /></div>
            <div><span className="fact">{sar(f.opening)}</span><span className="note">Cash plus undrawn facilities today</span></div>
          </section>
          <h2 className="section">Cash over the next 13 weeks</h2>
          <FanChart weeks={f.weeks} minimum={f.minimum} />
          <details>
            <summary>Show as a table</summary>
            <table className="others compact">
              <thead><tr><th scope="col">Week from</th><th scope="col" className="num">1 in 10 low</th>
                <th scope="col" className="num">Median</th><th scope="col" className="num">1 in 10 high</th></tr></thead>
              <tbody>{f.weeks.map((w) => (
                <tr key={w.start}><td>{w.start}</td><td className="num">{sar(w.p10)}</td>
                  <td className="num">{sar(w.p50)}</td><td className="num">{sar(w.p90)}</td></tr>
              ))}</tbody>
            </table>
          </details>
          <p className="note">The minimum is the facility&rsquo;s cash covenant where one exists, otherwise the
            company&rsquo;s cash policy. Facility terms come from the client&rsquo;s structured file until the document
            reader is built.</p>
        </>
      )}
    </CompanyShell>
  );
}
