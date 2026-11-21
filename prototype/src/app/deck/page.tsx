import { Badge } from "@astryxdesign/core/Badge";
import { acquisition, companies, DEFAULT_PERIOD, kpis } from "@/lib/api";
import { formatValue, monthLabel, sar } from "@/lib/format";

// Deck format pilot, option A (§17.5): slides 1, 11 and 20 as web slides rendered live from the results API. Compare
// with option B, the python-pptx deck (engine/runtime/deck/deck.pptx). Print to PDF at 16:9 from the browser.
const LABEL = "Example Holding — made-up data";

function Slide({ n, kicker, title, children }: { n: number; kicker?: string; title: string; children?: React.ReactNode }) {
  return (
    <section className="slide" aria-label={`Slide ${n}`}>
      <p className="slide-label"><Badge variant="error" label={LABEL} /></p>
      {kicker && <p className="note">{kicker}</p>}
      <h2>{title}</h2>
      {children}
      <p className="slide-foot note">{n}</p>
    </section>
  );
}

export default async function DeckPilot() {
  const [list, values, deal] = await Promise.all([companies(), kpis("EH-01", DEFAULT_PERIOD), acquisition()]);
  const byId = new Map(values.map((k) => [k.kpi_id, k]));
  const tile = (id: string) => { const k = byId.get(id); return k ? `${formatValue(k)} (${k.status})` : "Needs data"; };
  const d = deal.decision;
  return (
    <main className="deck">
      <p className="note">Format pilot, option A: web slides. The decision is recorded in docs/plans/progress.md.</p>
      <Slide n={1} title={`From ${list.length} ledgers to one decision system`}>
        <p className="slide-body">Group finance intelligence on Example Holding&rsquo;s books, as of {monthLabel(DEFAULT_PERIOD)}.</p>
        <p className="note">Prepared for TXG Group</p>
      </Slide>
      <Slide n={11} kicker="Company page · EH-01" title="Every company on one page">
        <ul className="slide-body">
          <li>Cash conversion {tile("HL-5")}</li>
          <li>Net debt to EBITDA {tile("HL-8")}</li>
          <li>Liquidity low point {tile("HL-7")}</li>
        </ul>
      </Slide>
      <Slide n={20} kicker="Story S10 · TGT-01" title={`The price that still creates value: ${sar(d.walk_away_ev)}`}>
        <ul className="slide-body">
          <li>Asking {sar(deal.ask_ev)}: a {Math.round(d.chance_at_ask * 100)}% chance it creates value</li>
          <li>Standalone value {sar(d.value_p10)} to {sar(d.value_p90)}, middle {sar(d.value_p50)}</li>
        </ul>
      </Slide>
    </main>
  );
}
