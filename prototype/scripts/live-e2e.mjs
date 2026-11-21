// End-to-end check of live updates (§16.8): an open heat-grid updates by itself, without a reload and within 10
// seconds, when the change feed delivers S12's corrected trial balance (feed seq 5450, EH-03 August 2026).
//
// Needs a results API started with a feed token and its own record (so the hold exists and the demo record is left
// alone), and a prototype pointed at it, for example:
//   TXG_RUNTIME=/tmp/txg-e2e TXG_PORT=8711 TXG_FEED_TOKEN=e2e python -m txg.api.main
//   TXG_API_URL=http://127.0.0.1:8711 npx next start -p 3001
//   BASE=http://localhost:3001 API=http://127.0.0.1:8711 TOKEN=e2e npm run e2e:live
import { readFileSync } from "node:fs";
import { chromium } from "playwright-core";

const BASE = process.env.BASE ?? "http://localhost:3001";
const API = process.env.API ?? "http://127.0.0.1:8711";
const TOKEN = process.env.TOKEN ?? "";
const FEED = process.env.FEED ?? new URL("../../data/txg-example-holding-uploads-2026-11-20/feed/changes.jsonl", import.meta.url);
const CHROME = process.env.CHROME ?? "/usr/bin/google-chrome";
const LIMIT_MS = 10_000;

const event = readFileSync(FEED, "utf8").split("\n").filter(Boolean).map((l) => JSON.parse(l)).find((e) => e.seq === 5450);
const browser = await chromium.launch({ executablePath: CHROME, headless: true });
const failures = [];
try {
  const context = await browser.newContext({ viewport: { width: 1400, height: 900 } });
  await context.addCookies([{ name: "txg-role", value: "ceo", url: BASE }]);
  const page = await context.newPage();
  const errors = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  await page.goto(`${BASE}/?period=2026-08&show=all&sort=code`);
  const row = page.locator("tbody tr", { hasText: "EH-03" });
  if (!(await row.innerText()).includes("On hold")) failures.push("EH-03 August is not on hold before the change");
  await page.evaluate(() => { window.__sameDocument = true; });
  await page.locator('.live[data-live="live"]').waitFor({ timeout: 10_000 });

  const started = Date.now();
  const res = await fetch(`${API}/changes?token=${encodeURIComponent(TOKEN)}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(event),
  });
  if (!res.ok) failures.push(`the API refused the change: ${res.status} ${await res.text()}`);
  try {
    await page.waitForFunction(() => {
      const tr = [...document.querySelectorAll("tbody tr")].find((r) => r.textContent.includes("EH-03"));
      return tr && !tr.textContent.includes("On hold");
    }, null, { timeout: LIMIT_MS });
  } catch {
    failures.push(`EH-03 still on hold ${LIMIT_MS / 1000} s after the change`);
  }
  const elapsed = Date.now() - started;
  if (!(await page.evaluate(() => window.__sameDocument === true))) failures.push("the page reloaded");
  const status = await page.locator(".live").innerText();
  if (!status.includes("EH-03 change 5450")) failures.push(`live status does not name the change: "${status}"`);
  if (errors.length) failures.push(`console errors: ${errors.join(" | ")}`);
  console.log(`${failures.length ? "FAIL" : "PASS"} heat-grid updated live in ${elapsed} ms (limit ${LIMIT_MS} ms); ` +
              `status "${status.trim()}"`);
} finally {
  await browser.close();
}
for (const f of failures) console.log(`  - ${f}`);
process.exit(failures.length ? 1 : 0);
