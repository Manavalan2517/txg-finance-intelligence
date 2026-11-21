// Screens for the deck (§17.3): the running prototype captured by a headless browser at a fixed size, light mode.
// Run with both servers up: `npm run deck:screens` (OUT defaults to ../engine/runtime/deck/screens).
import { mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";

const BASE = process.env.BASE ?? "http://localhost:3000";
const OUT = process.env.OUT ?? fileURLToPath(new URL("../../engine/runtime/deck/screens/", import.meta.url));
const CHROME = process.env.CHROME ?? "/usr/bin/google-chrome";
const P = "period=2026-10";
const SHOTS = [
  ["group", "ceo", `/?${P}`],
  ["company-EH-01", "ceo", `/company/EH-01?${P}`],
  ["kpi-EH-01-RC-1", "ceo", `/company/EH-01?${P}&kpi=RC-1_days_late`],
  ["company-EH-08-HL-3", "ceo", `/company/EH-08?${P}&kpi=HL-3`],
  ["cash-EH-01", "ceo", `/company/EH-01/cash?${P}`],
  ["receivables-EH-01", "ceo", `/company/EH-01/receivables?${P}`],
  ["integrity-EH-21", "cfo", `/company/EH-21/integrity?${P}`],
  ["acquisition", "ceo", "/acquisition"],
];

mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch({ executablePath: CHROME, headless: true });
let failed = 0;
try {
  for (const [name, role, path] of SHOTS) {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: "light",
                                               deviceScaleFactor: 2 });
    await context.addCookies([{ name: "txg-role", value: role, url: BASE }]);
    const page = await context.newPage();
    const errors = [];
    page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
    const res = await page.goto(`${BASE}${path}`, { waitUntil: "load" });
    await page.waitForTimeout(2500); // lazy charts finish drawing (the live stream keeps the network busy)
    if (path.includes("kpi=")) await page.locator(".drawer").scrollIntoViewIfNeeded();
    await page.screenshot({ path: `${OUT}/${name}.png` });
    const ok = res?.status() === 200 && errors.length === 0;
    if (!ok) failed += 1;
    console.log(`${ok ? "OK  " : "FAIL"} ${name} ${res?.status()}${errors.length ? ` console: ${errors.join(" | ")}` : ""}`);
    await context.close();
  }
} finally {
  await browser.close();
}
process.exit(failed ? 1 : 0);
