// End-to-end smoke check: every screen, rendered by the running prototype from the running results API, shows the
// story it is there to show. Run with both servers up: `npm run smoke` (BASE defaults to http://localhost:3000).
const BASE = process.env.BASE ?? "http://localhost:3000";
const P = "period=2026-10";

const CHECKS = [
  { role: "ceo", path: `/?${P}`, expect: ["companies have a headline measure that needs action", "Cash conversion"] },
  { role: "ceo", path: `/?${P}&show=act&sort=code`, expect: ["Needs action", "EH-01"] },
  { role: "ceo", path: `/company/EH-01?${P}`, expect: ["Cash conversion", "−29.3%", "Liquidity low point", "Act"] },
  { role: "ceo", path: `/company/EH-01?${P}&kpi=RC-1_days_late`, expect: ["Normal range", "Show as a table"] },
  { role: "ceo", path: `/company/EH-01/cash?${P}`, expect: ["Chance of falling below", "Cash over the next 13 weeks"] },
  { role: "ceo", path: `/company/EH-07/receivables?${P}`, expect: ["is 49% of the last 12 months", "Days past due"] },
  { role: "ceo", path: `/company/EH-21/integrity?${P}`, expect: ["Restricted page", "for the Group CFO"] },
  { role: "cfo", path: `/company/EH-21/integrity?${P}`, expect: ["IT-02", "Worth a look", "not proof of anything"] },
  { role: "ceo", path: `/company/EH-09/review?${P}`, expect: ["Restricted page"] },
  { role: "reviewer", path: `/company/EH-09/review?${P}`, expect: ["Mapping version", "Miscellaneous Income"] },
  { role: "ceo", path: "/acquisition", expect: ["Buy at or below SAR 401m", "namesake: different CR number", "TEST.4101"] },
  { role: "ceo", path: "/deck", expect: ["Format pilot, option A", "10 ledgers to one decision system",
                                        "The price that still creates value: SAR 401.4m", "Example Holding — made-up data"] },
];

const text = (html) => html.replace(/<!-- -->/g, "").replace(/&#x27;|&rsquo;/g, "'").replace(/&amp;/g, "&");

let failed = 0;
for (const { role, path, expect } of CHECKS) {
  const started = Date.now();
  const res = await fetch(`${BASE}${path}`, { headers: { Cookie: `txg-role=${role}` } });
  const body = text(await res.text());
  const missing = expect.filter((s) => !body.includes(s));
  const ok = res.status === 200 && missing.length === 0;
  if (!ok) failed += 1;
  console.log(`${ok ? "PASS" : "FAIL"} ${res.status} ${role.padEnd(8)} ${path} (${Date.now() - started} ms)` +
              (missing.length ? `\n     missing: ${missing.join(" | ")}` : ""));
}
console.log(`${CHECKS.length - failed} of ${CHECKS.length} screens passed`);
process.exit(failed ? 1 : 0);
