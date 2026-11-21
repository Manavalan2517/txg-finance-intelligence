import { Badge } from "@astryxdesign/core/Badge";
import { Banner } from "@astryxdesign/core/Banner";
import { clean } from "@/components/CompanyShell";
import { acquisition } from "@/lib/api";
import { pct, sar } from "@/lib/format";

// The acquisition workspace (§14): identity by CR number, standalone value from listed peers, the verdict.
function Range({ p10, p50, p90, ask, walk }: { p10: number; p50: number; p90: number; ask: number; walk: number }) {
  const lo = Math.min(p10, walk) * 0.9;
  const hi = Math.max(p90, ask) * 1.05;
  const at = (v: number) => `${((v - lo) / (hi - lo)) * 100}%`;
  return (
    <div className="range" role="img"
         aria-label={`Likely value ${sar(p10)} to ${sar(p90)}, median ${sar(p50)}; walk-away ${sar(walk)}; asking ${sar(ask)}`}>
      <div className="range-band" style={{ insetInlineStart: at(p10), inlineSize: `calc(${at(p90)} - ${at(p10)})` }} />
      <div className="range-mark median" style={{ insetInlineStart: at(p50) }}><span>Median {sar(p50)}</span></div>
      <div className="range-mark walk" style={{ insetInlineStart: at(walk) }}><span>Walk-away {sar(walk)}</span></div>
      <div className="range-mark ask" style={{ insetInlineStart: at(ask) }}><span>Asking {sar(ask)}</span></div>
    </div>
  );
}

export default async function AcquisitionPage() {
  const a = await acquisition();
  const d = a.decision;
  const peers = [...a.peers].sort((x, y) => x.ev_ebitda - y.ev_ebitda);
  const years = Object.keys(a.target.ebitda).sort();
  return (
    <main className="wide">
      <p className="note">Acquisition workspace · {a.target.id} · made-up data</p>
      <h1 className="verdict">{d.verdict}: the asking price of {sar(a.ask_ev)} has a {pct(d.chance_at_ask, 0)} chance of
        being worth it on a standalone basis.</h1>
      <section className="facts" aria-label="Decision">
        <div><span className="fact">{sar(d.walk_away_ev)}</span><span className="note">Walk-away price at the board&rsquo;s {pct(a.board_confidence, 0)} confidence</span></div>
        <div><span className="fact">{pct(d.chance_at_ask, 0)}</span><span className="note">Chance the value reaches the asking price</span></div>
        <div><span className="fact">{sar(d.synergy_gap)}</span><span className="note">Gap synergies would have to close</span></div>
        <div><span className="fact">{(a.ask_ev / a.target.ebitda[years[years.length - 1]]).toFixed(1)}x</span>
          <span className="note">Asking price ÷ FY{years[years.length - 1]} EBITDA</span></div>
      </section>
      <h2 className="section">Standalone value, 1-in-10 low to 1-in-10 high</h2>
      <Range p10={d.value_p10} p50={d.value_p50} p90={d.value_p90} ask={a.ask_ev} walk={d.walk_away_ev} />
      <div className="stack">
        {d.notes.map((n) => <Banner key={n} status="info" title="Not yet in the value" description={n} />)}
      </div>
      <div className="two">
        <table className="others">
          <caption className="note" style={{ textAlign: "start" }}>Listed peers · EV ÷ EBITDA FY2025, leases excluded both sides</caption>
          <thead><tr><th scope="col">Peer</th><th scope="col">Ticker</th><th scope="col" className="num">EV ÷ EBITDA</th></tr></thead>
          <tbody>{peers.map((p) => (
            <tr key={p.ticker}><th scope="row">{p.name}</th><td>{p.ticker}</td><td className="num">{p.ev_ebitda.toFixed(1)}x</td></tr>
          ))}</tbody>
        </table>
        <table className="others">
          <caption className="note" style={{ textAlign: "start" }}>From enterprise value to equity, FY2025</caption>
          <tbody>
            {Object.entries(a.bridge.items).map(([k, v]) => (
              <tr key={k}><th scope="row">Less {k.toLowerCase()}</th><td className="num">{sar(v)}</td></tr>
            ))}
            <tr><th scope="row">Plus cash</th><td className="num">{sar(a.bridge.cash)}</td></tr>
          </tbody>
        </table>
      </div>
      <h2 className="section">Target identity and the candidate screen</h2>
      <p className="note">The target is {clean(a.target.name)}, CR {a.target.cr_number}. Companies are matched by CR
        number only, never by name. Statements {a.target.checks_passed ? "balance in every year" : "do not balance"}.</p>
      <table className="others">
        <thead><tr><th scope="col">Candidate</th><th scope="col">Name</th><th scope="col">City</th>
          <th scope="col">Revenue (SAR m)</th><th scope="col">CR number</th><th scope="col">Identity</th></tr></thead>
        <tbody>{a.candidates.map((c) => (
          <tr key={c.candidate_id} className={c.identity ? "flag-row" : undefined}>
            <td>{c.candidate_id}</td><th scope="row">{clean(c.name)}</th><td>{c.city}</td><td>{c.revenue_band_sar_m}</td>
            <td>{c.cr_number}</td>
            <td>{c.identity ? <Badge variant="warning" label={`▲ ${c.identity}`} /> : <span className="note">—</span>}</td>
          </tr>
        ))}</tbody>
      </table>
    </main>
  );
}
