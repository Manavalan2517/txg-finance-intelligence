import Link from "next/link";
import { Badge } from "@astryxdesign/core/Badge";
import { Banner } from "@astryxdesign/core/Banner";
import { CompanyShell } from "@/components/CompanyShell";
import { StatusLine } from "@/components/Status";
import { SeriesChart } from "@/components/lazy-charts";
import { ApiRefusal, kpis, periodFrom, series, type Kpi } from "@/lib/api";
import { formatNumber, formatValue } from "@/lib/format";

// The headline band (§11.1): four pairs. A measure the engine cannot compute says so, never a typed number.
const PAIRS: [string, string[]][] = [
  ["Grow", ["HL-1_raw", "HL-2"]],
  ["Earn", ["HL-3", "HL-4_roic"]],
  ["Cash", ["HL-5", "HL-6"]],
  ["Survive", ["HL-7", "HL-8"]],
];
const SIMULATED = new Set(["HL-2", "HL-7"]);

function Tile({ k, id, href }: { k?: Kpi; id: string; href: string }) {
  const body = (
    <>
      <div className="value">{k ? formatValue(k) : "Needs data"}</div>
      <div className="name">{k?.name ?? id}</div>
      <StatusLine k={k} />
      {k?.provisional && <Badge variant="info" label="Provisional" />}
    </>
  );
  return SIMULATED.has(id) || !k ? <div className="tile">{body}</div>
    : <Link className="tile tile-link" href={href} scroll={false}>{body}</Link>;
}

async function Drawer({ code, kpi, period, close }: { code: string; kpi: string; period: string; close: string }) {
  const s = await series(code, kpi, period);
  return (
    <section className="drawer" aria-labelledby="drawer-title">
      <div className="drawer-head">
        <h2 id="drawer-title">{s.name}</h2>
        <Link href={close} scroll={false}>Close</Link>
      </div>
      {s.lower != null && s.upper != null && (
        <p className="note">Normal range {formatNumber(s.lower, s.unit)} to {formatNumber(s.upper, s.unit)}, from the
          24 months before the latest three (§12.2).</p>
      )}
      <SeriesChart months={s.months} values={s.values} lower={s.lower} upper={s.upper} unit={s.unit} name={s.name} />
      <details>
        <summary>Show as a table</summary>
        <table className="others compact">
          <thead><tr><th scope="col">Month</th><th scope="col" className="num">{s.name}</th></tr></thead>
          <tbody>
            {s.months.map((m, i) => (
              <tr key={m}><td>{m}</td><td className="num">{s.values[i] == null ? "n.m." : formatNumber(s.values[i]!, s.unit)}</td></tr>
            ))}
          </tbody>
        </table>
      </details>
    </section>
  );
}

export default async function CompanyPage({ params, searchParams }: {
  params: Promise<{ code: string }>; searchParams: Promise<{ period?: string; kpi?: string }>;
}) {
  const { code } = await params;
  const sp = await searchParams;
  const period = periodFrom(sp.period);
  let values: Kpi[] = [];
  let heldNote: string | null = null;
  try {
    values = await kpis(code, period);
  } catch (e) {
    const held = e instanceof ApiRefusal ? e.held : null;
    if (!held) throw e;
    heldNote = `${period} is on hold: ${held.reason}. Nothing is shown until the data ties` +
      (held.last_good_month ? `; the last good month is ${held.last_good_month}.` : ".");
  }
  const byId = new Map(values.map((k) => [k.kpi_id, k]));
  const headline = new Set(PAIRS.flatMap(([, ids]) => ids));
  const dependsOn = values[0]?.depends_on_held_months ?? [];
  const base = `/company/${code}?period=${period}`;
  const open = sp.kpi && byId.has(sp.kpi) && !SIMULATED.has(sp.kpi) ? sp.kpi : null;
  return (
    <CompanyShell code={code} period={period} tab="Overview">
      {heldNote && <Banner status="warning" title="Month on hold" description={heldNote} />}
      {dependsOn.length > 0 && (
        <Banner status="warning" title="Includes a month on hold"
                description={`These figures include ${dependsOn.join(", ")}, which is on hold until its trial balance ties.`} />
      )}
      {!heldNote && (
        <>
          <section className="pairs" aria-label="Headline measures">
            {PAIRS.map(([label, ids]) => (
              <div className="pair" key={label}>
                <h2>{label}</h2>
                {ids.map((id) => <Tile key={id} id={id} k={byId.get(id)} href={`${base}&kpi=${id}`} />)}
              </div>
            ))}
          </section>
          {open && <Drawer code={code} kpi={open} period={period} close={base} />}
          <table className="others">
            <caption className="note" style={{ textAlign: "start" }}>Supporting measures · select one to see its history</caption>
            <tbody>
              {values.filter((k) => !headline.has(k.kpi_id)).map((k) => (
                <tr key={k.kpi_id}>
                  <th scope="row"><Link href={`${base}&kpi=${k.kpi_id}`} scroll={false}>{k.name}</Link></th>
                  <td><StatusLine k={k} /></td>
                  <td className="num">{formatValue(k)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </CompanyShell>
  );
}
