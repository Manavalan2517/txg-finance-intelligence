# Example Holding – generated books (ten companies)

Made-up books for ten Example Holding companies, in Zoho Books' format, with an answer key and checks. This set replaces the three-company step 1 delivery (EH-01, EH-08 and EH-14 are unchanged).
Every name, number and identifier is invented (identifiers use the reserved `TEST-` format).

| Code | Company | Chart of accounts | Stories |
|---|---|---|---|
| EH-01 | Contracting A | B (Arabic) | S1: two government customers pay 38 days later from January 2026; S9 |
| EH-02 | Contracting B | A (English) | S6: buys from EH-05 but has not booked one invoice; S9 |
| EH-03 | Contracting C | E (Arabic with English abbreviations) | S9 (mild) |
| EH-05 | Building Materials A | A (English) | S5: margin up about a point; S6: sells to EH-02 |
| EH-06 | Building Materials B | B (Arabic) | S5 |
| EH-07 | Industrial Supplies | D (UK-style English) | S5: lowest margin, grows about 45%; S8: one new customer grows to about half of revenue |
| EH-08 | Food Distribution A | D (UK-style English) | S2: purchase prices of 60% of items +4.1% from October 2025, selling prices +1.2%; 23% of stock bought in euros |
| EH-09 | Food Distribution B | C (English / Arabic) | S13: "Miscellaneous income / إيرادات متنوعة" carries recurring service revenue |
| EH-14 | Retail A (home and lifestyle) | C (English / Arabic) | S4: normal Ramadan effect; nine new stores in 2025 with weak returns |
| EH-21 | Facility Management A | A (English) | S7: bills bunched below the SAR 50,000 approval limit, 40 journals entered late into closed months, Friday postings by a rarely-posting user; S9 |

S9 (government payment delays rise from February 2026) runs across EH-01, EH-02, EH-03 and EH-21, for the heat-grid.
S3 (healthcare claims) and S12 (printed trial balance mismatch) are not in this set: S12 is planted in the printed
trial balances in step 3. S10 (the acquisition target) and S11 (budgets) also come in step 3.

Books run from 1 January 2023 (go-live) to 19 November 2026. October 2026 is the last closed month; November is
open, so its month-end entries (accruals, cost of sales, depreciation, VAT) are not posted yet.

Start with `QUICK_LOOK.md` (headline numbers per company) and `validation_report.md` (every check, all passing).

## Folder layout

- `data/zoho/<code>/` – the books, one JSON file per record type, as Zoho Books' API returns them
  (`{"code": 0, "message": "success", "invoices": [...]}`), one record per line. Amounts in SAR.
  - `organization`, `users`, `taxes`, `currencies`, `chartofaccounts`, `bankaccounts`
  - `contacts`, `items`, `locations` (retail stores), `projects` (contractor)
  - `invoices`, `creditnotes`, `customerpayments`, `salesreceipts` (retail point of sale)
  - `purchaseorders`, `bills`, `vendorpayments`, `expenses`, `inventoryadjustments`, `journals`
  - `banktransactions` (statement lines; a few are left uncategorised on purpose)
  - `openingbalances` (every balance-sheet account at go-live), `transactionlocks` (month-end lock history)
  - `account_transactions.csv` – the general ledger: every posting from go-live, like Zoho's account registers
  - `manifest.json` – record counts and file hashes
- `data/answer-key/<code>/` – what the engine should find, computed from the generator's own ledger:
  `chart_mapping.csv` (true standard account for every account), `monthly_statements.csv`, `kpis_monthly.csv`
  (the KPI values, closed months only), `counterparties.csv` (true class: government, private…),
  `payroll_register.csv`, `close_calendar.csv`, plus sector files (projects, item prices, stores, store sales).
- `generator/` – the code that produced everything (`python3 generate.py --out out`, standard library only,
  Python 3.9+, about one minute). The same configuration gives byte-identical files (`hashes.json`).

## Conventions the connector needs

- **Migration at go-live.** Invoices and bills dated before 1 January 2023 that were still open are included,
  with their balance at go-live in the custom field `cf_balance_at_go_live`; payments before go-live are not.
  Opening receivables and payables equal the sum of those balances.
- **Line items** carry `account_id` (names come from the chart of accounts). Discounts appear as `discount`
  and `discount_amount`. Store-level lines carry a `Store` tag; retail documents carry `location_id`.
- **Retention (contractor).** The client withholds 10% of each certificate; it stays as the invoice's open
  balance until released (half at handover, half after the defects period). Only the invoice notes say so,
  as in real books: the model tags retention.
- **Unbilled work (contractor)** is accrued at month end and reversed on the 1st of the next month.
- **Foreign-currency bills** carry `exchange_rate`; customs duty, import VAT and clearing come on a separate
  bill from the clearing agent.
- **Intercompany.** EH-05 sells building materials to EH-02 on 60-day terms. Both sides carry the delivery-note
  number (invoice `reference_number` at EH-05, bill number at EH-02), which is the matching key.
- **Facility management (EH-21)** uses the contractor engine with monthly service contracts and no retention.
- **Real time.** The change feed that replays edits after the last closed month comes in step 3.

## Not yet confirmed against a live Zoho organisation (VERIFY)

Field names follow Zoho Books' API documentation but were not checked on a real organisation:
the `salesreceipts`, `locations`, `inventoryadjustments` and `banktransactions` record shapes; reporting-tag
fields on line items; invoice and bill `status` values; `payment_made` and `credits_applied`;
the custom-field `api_name` format; the opening-balance object; the transaction-lock history (our own file,
not an API object). Confirm with one test call per record type.

## Simplifications

- Two warm-up years (2021–2022) are simulated to reach a steady state; only their open documents and the
  balances at go-live are exported.
- The contractor and the distributor expense their leases (IFRS for SMEs); the retailer applies IFRS 16.
- Zakat is accrued at 2.5% of an approximate Zakat base and paid on 30 April; VAT is filed monthly.
- Payroll is posted as one journal a month per company; the payroll and GOSI files arrive in step 3.
- Market rates (SAIBOR, EUR, CNY) are rounded approximations, not market data.

## Next

- Step 3: budgets (with S11), facility letters and covenants, payroll, sector uploads, Zoho's printed trial
  balance per closed month, the acquisition data, and the change feed with its replay script.
