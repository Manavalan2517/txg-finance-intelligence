# Example Holding – uploads, change feed and acquisition data

This add-on goes with the books package (`txg-example-holding-2026-11-20`). The books are unchanged. Everything here
is made up and computed from the same generated books, so it agrees with them to the halala.

## What is in it

| Folder | Contents | Used by |
|---|---|---|
| `uploads/<code>/trial_balances/` | Zoho's Trial Balance report for each closed month (Jan 2023–Oct 2026), CSV: balance-sheet accounts at the month end, income and expense accounts for the year to date, earlier years' profit inside retained earnings | CK-03, TR-1 |
| `uploads/<code>/budgets/` | The board-approved budget for each year 2023–2026, monthly, by line (revenue to net profit) | HL-2, PF-5, TR-3 |
| `uploads/<code>/facility_letters/` | Facility offer letters (PDF, prose): facilities, pricing, repayment schedules, security, covenants with their definitions | HL-7, HL-8, FG-1, FG-2, PY-1, PY-3 |
| `uploads/<code>/payroll_gosi.csv`, `headcount.csv` | Monthly payroll and GOSI by department; headcount with Saudi and non-Saudi staff | PF-4, PY-4 |
| `uploads/EH-14/stores.csv`, `pos_monthly.csv` | Store list with selling area; monthly transactions, units and net sales per store | RET-2, RET-3 |
| `uploads/<code>/settings.json` | Approval limit (stands in for the delegation-of-authority document), VAT filing, year end, cash policy | IT-01 (S7) |
| `feed/changes.jsonl` | The change feed: 5,454 events, one JSON object per line, in time order | Real time |
| `acquisition/` | The target's data room, 30 candidates, 8 listed peers | Acquisition workspace |
| `answer-key-additions/` | The truth for the files above: which trial balances tie, budget against actual by quarter, facility terms and covenants as structured data, the target's facts | Tests |

## Planted in these files

- **S11 (EH-08):** revenue budgets above actual in 7 of the last 8 quarters, about 10% on average.
- **S12 (EH-03):** the August 2026 trial balance was printed before the month's depreciation journal, so it does not tie;
  the corrected file arrives through the change feed and the hold should lift by itself.
- **EH-01 covenants:** net debt ÷ EBITDA at most 3.50 (it reaches 3.06 in October 2026), debt service cover at least 1.25,
  cash plus undrawn facility at least SAR 40m at all times (it is SAR 45.8m at the end of October).
- **EH-14** defines EBITDA before IFRS 16 in its facility letter, so the covenant figure differs from the reported one.
- **S10 (target):** asking enterprise value SAR 520m, 11.8 times FY2025 EBITDA. The verdict is for the engines to compute.
  Debt-like items to find: a change-of-control prepayment, lease liabilities, end-of-service benefits, a Zakat assessment
  under appeal. Also related-party rent and a large customer contract ending in March 2027.
- **Candidates:** two namesakes (a refrigeration equipment seller and a cold-room contractor) that are not cold-chain
  operators, to test "peers on facts, not names".

## The change feed

Each line is one event: `seq`, `ts` (Riyadh time), `company`, `op` (`create`, `update` or `upload`), `record_type`, `id`, the full
`record` in Zoho's format, its general-ledger `postings` and `bank_lines`, and for updates the `before` record and
`postings_before`.

- **Part A (5,442 events):** everything entered from 1 November 2026 00:00 to the data end: new documents, payments and
  the October close entries (October moves from provisional to final).
- **Part B (12 events, after the data end):** a certificate reduced after invoicing (EH-01), a back-dated provision into a
  closed month (EH-01), the missing intercompany bill booked (EH-02, story S6 clears), the corrected trial balance (EH-03,
  story S12 clears), a journal in a closed month edited on a Friday evening (EH-21, story S7), and ordinary new activity.

```
python3 replay.py base --data <books>/data/zoho --feed feed/changes.jsonl --out live
python3 replay.py play --feed feed/changes.jsonl --live live --root . --speed 600
python3 replay.py play --feed feed/changes.jsonl --live live --root . --post http://localhost:8000/events
```

`base` builds the state before the feed (the delivered books minus the records part A creates). `play` applies the events
in order; `--speed` replays faster than real time, and `--post` sends each event to an endpoint such as the engine's connector.
Checked: building the base and replaying part A reproduces the delivered books exactly.

Note: Zoho's `status` and `balance` fields on invoices and bills reflect the data end; the engine should compute
balances from payments and credit notes, not read those fields.

## Regenerating

`generator/` holds the full generator. `python3 generate.py --out out` rebuilds the books, the answer key and everything
here in about 70 seconds (standard library, Python 3.9+), byte-identical every time.
