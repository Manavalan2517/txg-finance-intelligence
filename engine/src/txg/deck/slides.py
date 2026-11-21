"""The storyline (§17.2): 23 slides and appendices A1–A5. Every number is a fact (`w.n`) or a chart of facts; text
slides carry no numbers at all. Where the engine has not built what a slide needs yet, the slide says so plainly
instead of showing a number."""
from pathlib import Path

from pptx.util import Inches

from txg.deck.engine import DIVISION, Facts
from txg.deck.writer import DeckWriter

LEFT_W, IMG_X, IMG_W = Inches(4.3), Inches(5.15), Inches(7.6)
NOT_BUILT = "Not yet built in the engine"


def _screen(w: DeckWriter, title: str, kicker: str, lines: list[str], image: Path) -> None:
    s = w.slide(title, kicker=kicker)
    w.bullets(s, lines, w=LEFT_W, size=15)
    w.image(s, image, x=IMG_X, y=Inches(1.8), w=IMG_W)


def opening(w: DeckWriter, f: Facts) -> None:
    s = w.slide(f"From {w.n(f['companies'])} ledgers to one decision system", txg=True)
    w.text(s, f"Group finance intelligence on Example Holding's books, as of {w.n(f['as_of'])}.\n"
              "Code counts, the model reads, people decide, the record remembers.", y=Inches(2.3), size=20)
    s = w.slide("You asked twelve questions; here is where each is answered", kicker="The question map (§3.3)")
    w.table(s, ["Question", "Where it is answered"], [
        ["Is each company really performing?", "Headline Earn pair; company page"],
        ["What is going well or wrong?", "Trend markers under the group false-alarm limit"],
        ["What must be paid, and when?", "Cash page; obligations from facility schedules"],
        ["What is pending?", "Company page panels (sector modules pending)"],
        ["Will we have the cash?", "Headline Survive pair; thirteen-week cash simulation"],
        ["Are receivables healthy?", "Receivables page: days late, ageing, concentration"],
        ["Which driver is at risk?", "Sector modules (not yet built)"],
        ["Is a company getting fragile?", "Covenant headroom, liquidity low point"],
        ["Whose numbers can we trust?", "Trial-balance tie-out and automatic holds"],
        ["What is suspicious?", "Integrity page, CFO only"],
        ["Is the group diversified, and what is it worth?", "Group heat-grid (value map not yet built)"],
        ["Is this acquisition worth it, and at what price?", "Acquisition workspace"]], size=12)
    s = w.slide("Normal dashboards fail in eight ways", kicker="The design rationale (§4)")
    w.table(s, ["How a normal dashboard fails", "What this product does instead"], [
        ["It flags noise", "A group-wide false-alarm limit across every company and measure"],
        ["One rule for every business", "Peer bands per line of business, own normal range until they exist"],
        ["Ramadan moves", "Hijri holiday adjustment before any comparison"],
        ["The total lies", "Every group change split into company performance and mix"],
        ["Profit is not cash", "Cash conversion and the liquidity low point are headline measures"],
        ["It looks backwards", "Forecasts with ranges; the chance of hitting budget"],
        ["It trusts the books", "Trial balances tied before any measure; integrity tests"],
        ["Deals judged on earnings per share", "Value against the cost of capital; a walk-away price"]], size=13)


def evidence(w: DeckWriter, f: Facts) -> None:
    s = w.slide(f"A normal dashboard raised {w.n(f['naive_alarms'])} alarms this month; ours raised "
                f"{w.n(f['kept_signals'])}", kicker=f"Signals, {w.n(f['as_of'])}")
    w.bar_chart(s, "Alarms raised", ["Fixed threshold per reading", "Group false-alarm limit"],
                [f["naive_alarms"], f["kept_signals"]])
    w.bullets(s, [f"{w.n(f['signal_tests'])} signal tests across {w.n(f['companies'])} companies",
                  f"Benjamini–Hochberg at q = {w.n(f['fdr_q'])}, pooled across the group",
                  "Everything not raised is kept, with its reason, in the \"not alarmed\" log"],
              x=Inches(8.4), w=Inches(4.3), size=15)
    s = w.slide("One rule cannot judge every business", kicker="Peer bands (§12.5)")
    w.bullets(s, [f"{NOT_BUILT}: peer bands need sector peers, which have not been delivered for the prototype.",
                  "Until then every level status uses the company's own normal range, and the screen says so.",
                  "The current ratio also needs the current portion of term loans from the facility schedules."])
    s = w.slide("Ramadan moves: the March drop was the calendar", kicker="Story S4 · EH-14 retail")
    w.bar_chart(s, "March sales against last March (%)", ["As booked", "Holiday-adjusted"], [f["s4.raw"], f["s4.adjusted"]])
    w.bullets(s, [f"Booked sales: {w.n(f['s4.raw'])} on last March", f"After the holiday adjustment: {w.n(f['s4.adjusted'])}",
                  "Ramadan filled last March; this year it started in February", "The drop is logged as not alarmed"],
              x=Inches(8.4), w=Inches(4.3), size=15)
    _division(w, f)
    _screen(w, "Profitable is not liquid", "Story S1 · EH-01 contracting", [
        f"Customers pay {w.n(f['EH-01.RC-1_days_late'])} days late on average",
        f"SAR {w.n(f['EH-01.retention_held'])} held back as retention",
        f"Liquidity low point SAR {w.n(f['EH-01.HL-7'])} against a SAR {w.n(f['EH-01.cash_minimum'])} minimum",
        f"Cash conversion {w.n(f['EH-01.HL-5'])}: {w.n(f['EH-01.HL-5.status'])}"],
        w.screens / "receivables-EH-01.png")


def _division(w: DeckWriter, f: Facts) -> None:
    s = w.slide("Every company improved; the division got worse", kicker="Story S5 · building materials")
    rows = [[c, w.n(f[f"s5.{c}.m0"]), w.n(f[f"s5.{c}.m1"])] for c in DIVISION]
    rows.append(["Division", w.n(f["s5.division_m0"]), w.n(f["s5.division_m1"])])
    w.table(s, ["Gross margin, last twelve months", "A year earlier", "Now"], rows, w=Inches(6.4), size=14)
    w.bar_chart(s, "Division margin change (percentage points)", ["Performance", "Mix"],
                [f["s5.performance"], f["s5.mix"]], x=Inches(7.3), w=Inches(5.4))
    w.text(s, f"Each company's margin rose ({w.n(f['s5.performance'])} of performance), but sales moved to the "
              f"lower-margin company ({w.n(f['s5.mix'])} of mix).", y=Inches(4.4), w=Inches(6.4), h=Inches(1.5), size=15)


def product(w: DeckWriter, f: Facts) -> None:
    s = w.slide("Code counts, the model reads, people decide, the record remembers", kicker="Principles (§5)")
    w.bullets(s, ["Code does only what is identical for every company: arithmetic, statistics, simulations, checks (R2)",
                  "The model makes the per-company calls, and never produces a number (R3, R5)",
                  "Every model output passes a code check; a failed check is a finding, not a dead end (R6, R7)",
                  "Identity by identifiers, never by names (R9)",
                  "Nothing waits for a person: decisions are applied, logged and open to review (R16)",
                  "One record: any month replays to the same answer (R13)"], size=17)
    s = w.slide("From Zoho to a live, tied, mapped ledger", kicker="Architecture and the real-time flow (§6.3)")
    w.bullets(s, ["Zoho Books (read only) → snapshots → normalised ledger",
                  "Trial balance tied to Zoho's own report; a month that does not tie is held automatically",
                  "Accounts mapped to one standard chart; material accounts read twice",
                  "Measures, statistics and simulations computed by code from the standard ledger",
                  "A changed record is applied at once; every open screen refreshes itself within seconds",
                  "Screens and this deck read only the results API"], size=17)
    _screen(w, "Every company on one page", "Company page · EH-01", [
        f"Cash conversion {w.n(f['EH-01.HL-5'])} ({w.n(f['EH-01.HL-5.status'])})",
        f"Net debt to EBITDA {w.n(f['EH-01.HL-8'])} ({w.n(f['EH-01.HL-8.status'])})",
        f"Liquidity low point SAR {w.n(f['EH-01.HL-7'])} ({w.n(f['EH-01.HL-7.status'])})",
        "Four pairs: grow, earn, cash, survive"], w.screens / "company-EH-01.png")
    _screen(w, "Two signals on every number", "Story S2 · EH-08 early warning", [
        f"EBITDA margin {w.n(f['EH-08.HL-3'])}",
        f"Where it stands: {w.n(f['EH-08.HL-3.status'])}", f"Where it is heading: {w.n(f['EH-08.HL-3.trend'])}",
        "Colour always comes with an icon and a word"], w.screens / "company-EH-08-HL-3.png")
    _screen(w, "Every number has a receipt", "Lineage", [
        "Every measure opens its history with the normal range and a table view",
        "Every figure is stored with the record it came from",
        f"Drill-down from a measure to accounts and invoices on screen: {NOT_BUILT.lower()}"],
        w.screens / "kpi-EH-01-RC-1.png")
    s = w.slide("Cash and obligations, thirteen weeks ahead", kicker="Cash page · EH-01")
    weeks = [f[f"EH-01.cash_week{i}_p50"] for i in range(1, 14) if f"EH-01.cash_week{i}_p50" in f]
    w.bar_chart(s, "Median cash by week (SAR m)", [f"W{i}" for i in range(1, len(weeks) + 1)], weeks, w=Inches(7.6))
    w.bullets(s, [f"Minimum cash SAR {w.n(f['EH-01.cash_minimum'])}",
                  f"Chance of falling below it: {w.n(f['EH-01.cash_chance_below'])}",
                  f"One-in-ten low point SAR {w.n(f['EH-01.cash_low_p10'])}"], x=Inches(8.4), w=Inches(4.3), size=15)


def findings(w: DeckWriter, f: Facts) -> None:
    _screen(w, "Worth a look: what the ledger tests found", "Story S7 · EH-21, CFO only", [
        (f"{w.n(f['EH-21.IT-02.below'])} bills just below the SAR {w.n(f['EH-21.IT-02.limit'])} approval limit, "
         f"{w.n(f['EH-21.IT-02.above'])} just above"),
        f"{w.n(f['EH-21.IT-03.hits'])} journals back-dated into closed months",
        f"{w.n(f['EH-21.IT-06.hits'])} weekend or late-night postings by rarely-posting users",
        "Worth a look, not proof of anything"], w.screens / "integrity-EH-21.png")
    _screen(w, f"One column, many companies: {w.n(f['acting_companies'])} of {w.n(f['companies'])} need action",
            "Group heat-grid", ["Every company, the four headline pairs, status as colour, icon and word",
                                "Filter to what needs action; sort by most to act on",
                                "Government payment slowdown by customer class: needs the customer tagger"],
            w.screens / "group.png")
    s = w.slide("Where value is created and where it is destroyed", kicker="Return on invested capital")
    roic = sorted((k for k in f if k.endswith(".HL-4_roic")), key=lambda k: -f[k].number())
    w.bar_chart(s, "Return on invested capital, last twelve months (%)", [k.split(".")[0] for k in roic],
                [f[k] for k in roic], horizontal=True, w=Inches(7.6))
    w.bullets(s, ["Economic profit needs each company's cost of capital", f"{NOT_BUILT}: cost of capital and the value map"],
              x=Inches(8.4), w=Inches(4.3), size=15)


def acquisition(w: DeckWriter, f: Facts) -> None:
    s = w.slide("Acquisitions: from search to verdict", kicker="Acquisition flow (§14)")
    w.bullets(s, ["Search on facts: sector, region, size band, identity by commercial registration number",
                  "Read the data room twice; recompute the audited statements",
                  "Value against listed peers and the target's own variability",
                  "A walk-away price and the chance that paying the ask creates value"], size=17)
    s = w.slide("Finding targets on facts, not names", kicker="Shortlist")
    w.bullets(s, [f"{w.n(f['tgt.candidates'])} candidates in the made-up universe",
                  f"{w.n(f['tgt.namesakes'])} namesake caught: same name, different registration number, no price given",
                  f"Graded quotes from documents: {NOT_BUILT.lower()}"], size=17)
    s = w.slide(f"The price that still creates value: SAR {w.n(f['tgt.walk_away_ev'])}", kicker="Story S10 · TGT-01")
    w.bar_chart(s, "Value and price (SAR m)", ["Low (one in ten)", "Middle", "High (one in ten)", "Walk-away", "Asking"],
                [f["tgt.value_p10"], f["tgt.value_p50"], f["tgt.value_p90"], f["tgt.walk_away_ev"], f["tgt.ask"]],
                horizontal=True, w=Inches(7.6))
    w.bullets(s, [f"Asking SAR {w.n(f['tgt.ask'])}: a {w.n(f['tgt.chance_at_ask'])} chance it creates value",
                  f"{w.n(f['tgt.peers'])} listed peers at {w.n(f['tgt.peer_low'])} to {w.n(f['tgt.peer_high'])} EV/EBITDA",
                  "Synergies not yet in the value"], x=Inches(8.4), w=Inches(4.3), size=15)
    _screen(w, "The verdict on one page", "Acquisition workspace", [
        w.n(f["tgt.verdict"]), f"Walk-away SAR {w.n(f['tgt.walk_away_ev'])}",
        f"Chance at the asking price: {w.n(f['tgt.chance_at_ask'])}"], w.screens / "acquisition.png")


def closing(w: DeckWriter, f: Facts) -> None:
    s = w.slide("How we roll out", txg=True, kicker="Plan (§19)")
    w.bullets(s, ["A pilot of three companies, then all companies, then acquisitions",
                  "What we need from TXG: read-only Zoho access, facility documents, budgets, peers per sector",
                  "Review by the product lead after each piece"], size=18)
    s = w.slide("Why you can trust it", kicker="Methods, reproducibility, security")
    w.bullets(s, ["Every number in this deck is traced to a fact and recomputed by an audit before delivery",
                  "Any month replays to the same answer, checked by hash",
                  "Every model output passes a code check; held data is never published",
                  "Read-only access; data stays in the Kingdom where required"], size=17)


def appendix(w: DeckWriter, f: Facts) -> None:
    ids = sorted(k.removeprefix("kpi.").removesuffix(".name") for k in f if k.startswith("kpi."))
    half = (len(ids) + 1) // 2
    s = w.slide("Appendix A1: the measure catalogue", kicker="KPI registry (§10)")
    for col, chunk in enumerate((ids[:half], ids[half:])):
        w.table(s, ["ID", "Measure"], [[i, w.n(f[f"kpi.{i}.name"])] for i in chunk],
                x=Inches(0.6) + col * Inches(6.2), w=Inches(6.0), size=9, widths=(0.34, 0.66))
    s = w.slide("Appendix A2: sector modules", kicker="§10.6")
    w.bullets(s, [f"{NOT_BUILT}: contracting, retail, healthcare, logistics, hospitality and staffing modules",
                  "Each module adds its own drivers and leading indicators from sector operating data"])
    s = w.slide("Appendix A3: methods", kicker="With formulas and sources (§12)")
    w.bullets(s, ["Normal range: individuals and moving-range chart (Wheeler), on the measure as defined",
                  f"False-alarm limit: Benjamini–Hochberg across the group, q = {w.n(f['fdr_q'])}",
                  "Holiday adjustment: regression on Ramadan and Eid day shares by month (Hijri calendar)",
                  "Cash: thirteen weekly steps simulated from each company's own payment delays",
                  "Value: bootstrap of listed peers' EV/EBITDA times the target's EBITDA and its variability",
                  "Performance versus mix: exact split of a group margin change"], size=15)
    s = w.slide("Appendix A4: data and security", kicker="§6.6")
    w.bullets(s, ["Example Holding is made up; no client data was used",
                  "Read-only connections; secrets in a secrets manager, never in code or logs",
                  "Role-based access; the integrity page is for the CFO only and every view is logged"])
    s = w.slide("Appendix A5: glossary", kicker="Appendix A")
    w.table(s, ["Term", "Meaning"], [
        ["Normal range", "Where a measure usually sits, from its own history"],
        ["Held month", "A month whose trial balance does not tie; nothing from it is published"],
        ["Walk-away price", "The highest price that still creates value with the board's confidence"],
        ["Liquidity low point", "The lowest expected cash plus undrawn lines in the next thirteen weeks"],
        ["Mix", "The part of a group change caused by sales moving between companies"]], size=13)


SECTIONS = (opening, evidence, product, findings, acquisition, closing, appendix)
