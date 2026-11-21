# Example Holding – validation report

Generator 0.1.0 · data from 2023-01-01 to 2026-11-19 (warm-up from 2021-01-01, not exported) · every figure made up.

## EH-01 Contracting A

22 of 22 checks pass.

| Check | Result | Detail |
|---|---|---|
| Trial balance balances at every month end | PASS | largest imbalance SAR 0.00 |
| Receivables control account equals open invoices, every month | PASS | largest difference SAR 0.00 |
| Payables control account equals open bills, every month | PASS | largest difference SAR 0.00 |
| VAT input and output accounts are cleared to VAT payable at every close | PASS | largest residue SAR 0.00 |
| No bank or cash account is overdrawn at the end of any day | PASS | lowest end-of-day balances all ≥ 0 |
| Inventory is never negative at a month end | PASS | all ≥ 0 |
| No payment is dated before the invoice or bill it settles | PASS | 0 payments out of order |
| Every exported JSON file parses | PASS | 17 files read back |
| Line items, VAT and totals add up on every invoice, bill, receipt and credit note | PASS | 0 documents off by more than rounding |
| Every payment, credit note, contact and account reference resolves to an exported record | PASS | 0 unresolved references |
| Record IDs are unique | PASS | 23056 IDs, 0 duplicates |
| General ledger file: debits equal credits, and every transaction balances | PASS | debits SAR 16,996,175,487.96, credits SAR 16,996,175,487.96, unbalanced transactions 0 |
| Opening balances plus the general ledger file reproduce every account at every month end | PASS | largest difference SAR 0.00 |
| Opening receivables equal the go-live balances of the migrated invoices | PASS | opening SAR 189,517,723.68, migrated invoices SAR 189,517,723.68 |
| Categorised bank lines equal the bank accounts' movements in the ledger | PASS | largest difference SAR 0.00; 9 statement lines left uncategorised on purpose |
| No document is dated after the data end | PASS | 0 documents after 2026-11-19 |
| S1/S9: days late higher in January–October 2026 than a year earlier (by 8 days or more) | PASS | average days late (3-month basis) 2025 34.6, 2026 53.1, change +18.6 |
| S1/S9: DSO higher in October 2026 than a year earlier | PASS | DSO Oct 2025 134.9082, Oct 2026 157.0338 |
| S1/S9: liquidity (cash plus undrawn facility) lower than a year earlier | PASS | SAR m: Oct 2025 100.2, Oct 2026 45.8 |
| S1/S9: cash conversion (LTM) lower than a year earlier | PASS | Oct 2025 1.0029, Oct 2026 -0.2932 |
| Printed trial balances: every month re-derived from the exported ledger ties, except the planted one | PASS | 46 months tested; months that differ: none |
| Covenants are set and the company is within them at its latest test date | PASS | 2 facility letter(s); leverage limit 3.50x |

## EH-02 Contracting B

19 of 19 checks pass.

| Check | Result | Detail |
|---|---|---|
| Trial balance balances at every month end | PASS | largest imbalance SAR 0.00 |
| Receivables control account equals open invoices, every month | PASS | largest difference SAR 0.00 |
| Payables control account equals open bills, every month | PASS | largest difference SAR 0.00 |
| VAT input and output accounts are cleared to VAT payable at every close | PASS | largest residue SAR 0.00 |
| No bank or cash account is overdrawn at the end of any day | PASS | lowest end-of-day balances all ≥ 0 |
| Inventory is never negative at a month end | PASS | all ≥ 0 |
| No payment is dated before the invoice or bill it settles | PASS | 0 payments out of order |
| Every exported JSON file parses | PASS | 17 files read back |
| Line items, VAT and totals add up on every invoice, bill, receipt and credit note | PASS | 0 documents off by more than rounding |
| Every payment, credit note, contact and account reference resolves to an exported record | PASS | 0 unresolved references |
| Record IDs are unique | PASS | 18763 IDs, 0 duplicates |
| General ledger file: debits equal credits, and every transaction balances | PASS | debits SAR 11,942,913,510.24, credits SAR 11,942,913,510.24, unbalanced transactions 0 |
| Opening balances plus the general ledger file reproduce every account at every month end | PASS | largest difference SAR 0.00 |
| Opening receivables equal the go-live balances of the migrated invoices | PASS | opening SAR 151,223,041.96, migrated invoices SAR 151,223,041.96 |
| Categorised bank lines equal the bank accounts' movements in the ledger | PASS | largest difference SAR 0.00; 6 statement lines left uncategorised on purpose |
| No document is dated after the data end | PASS | 0 documents after 2026-11-19 |
| S9: days late higher in January–October 2026 than a year earlier | PASS | average days late (3-month basis) 2025 44.4, 2026 50.0, change +5.6 |
| Printed trial balances: every month re-derived from the exported ledger ties, except the planted one | PASS | 46 months tested; months that differ: none |
| Covenants are set and the company is within them at its latest test date | PASS | 1 facility letter(s); leverage limit 3.00x |

## EH-03 Contracting C

19 of 19 checks pass.

| Check | Result | Detail |
|---|---|---|
| Trial balance balances at every month end | PASS | largest imbalance SAR 0.00 |
| Receivables control account equals open invoices, every month | PASS | largest difference SAR 0.00 |
| Payables control account equals open bills, every month | PASS | largest difference SAR 0.00 |
| VAT input and output accounts are cleared to VAT payable at every close | PASS | largest residue SAR 0.00 |
| No bank or cash account is overdrawn at the end of any day | PASS | lowest end-of-day balances all ≥ 0 |
| Inventory is never negative at a month end | PASS | all ≥ 0 |
| No payment is dated before the invoice or bill it settles | PASS | 0 payments out of order |
| Every exported JSON file parses | PASS | 17 files read back |
| Line items, VAT and totals add up on every invoice, bill, receipt and credit note | PASS | 0 documents off by more than rounding |
| Every payment, credit note, contact and account reference resolves to an exported record | PASS | 0 unresolved references |
| Record IDs are unique | PASS | 14571 IDs, 0 duplicates |
| General ledger file: debits equal credits, and every transaction balances | PASS | debits SAR 8,719,983,682.08, credits SAR 8,719,983,682.08, unbalanced transactions 0 |
| Opening balances plus the general ledger file reproduce every account at every month end | PASS | largest difference SAR 0.00 |
| Opening receivables equal the go-live balances of the migrated invoices | PASS | opening SAR 107,844,110.78, migrated invoices SAR 107,844,110.78 |
| Categorised bank lines equal the bank accounts' movements in the ledger | PASS | largest difference SAR 0.00; 8 statement lines left uncategorised on purpose |
| No document is dated after the data end | PASS | 0 documents after 2026-11-19 |
| S9: days late higher in January–October 2026 than a year earlier | PASS | average days late (3-month basis) 2025 41.0, 2026 43.5, change +2.5 |
| Printed trial balances: every month re-derived from the exported ledger ties, except the planted one | PASS | 46 months tested; months that differ: ['2026-08'] (planted: 2026-08, story S12) |
| Covenants are set and the company is within them at its latest test date | PASS | 2 facility letter(s); leverage limit 3.00x |

## EH-05 Building Materials A

19 of 19 checks pass.

| Check | Result | Detail |
|---|---|---|
| Trial balance balances at every month end | PASS | largest imbalance SAR 0.00 |
| Receivables control account equals open invoices, every month | PASS | largest difference SAR 0.00 |
| Payables control account equals open bills, every month | PASS | largest difference SAR 0.00 |
| VAT input and output accounts are cleared to VAT payable at every close | PASS | largest residue SAR 0.00 |
| No bank or cash account is overdrawn at the end of any day | PASS | lowest end-of-day balances all ≥ 0 |
| Inventory is never negative at a month end | PASS | all ≥ 0 |
| Stock ledger equals the sum of the stock layers (first in, first out) | PASS | ledger SAR 32,890,374.23, layers SAR 32,890,374.23 |
| No payment is dated before the invoice or bill it settles | PASS | 0 payments out of order |
| Every exported JSON file parses | PASS | 19 files read back |
| Line items, VAT and totals add up on every invoice, bill, receipt and credit note | PASS | 0 documents off by more than rounding |
| Every payment, credit note, contact and account reference resolves to an exported record | PASS | 0 unresolved references |
| Record IDs are unique | PASS | 42107 IDs, 0 duplicates |
| General ledger file: debits equal credits, and every transaction balances | PASS | debits SAR 9,589,525,073.80, credits SAR 9,589,525,073.80, unbalanced transactions 0 |
| Opening balances plus the general ledger file reproduce every account at every month end | PASS | largest difference SAR 0.00 |
| Opening receivables equal the go-live balances of the migrated invoices | PASS | opening SAR 81,467,216.04, migrated invoices SAR 81,467,216.04 |
| Categorised bank lines equal the bank accounts' movements in the ledger | PASS | largest difference SAR 0.00; 6 statement lines left uncategorised on purpose |
| No document is dated after the data end | PASS | 0 documents after 2026-11-19 |
| Printed trial balances: every month re-derived from the exported ledger ties, except the planted one | PASS | 46 months tested; months that differ: none |
| Covenants are set and the company is within them at its latest test date | PASS | 1 facility letter(s); leverage limit 3.00x |

## EH-06 Building Materials B

19 of 19 checks pass.

| Check | Result | Detail |
|---|---|---|
| Trial balance balances at every month end | PASS | largest imbalance SAR 0.00 |
| Receivables control account equals open invoices, every month | PASS | largest difference SAR 0.00 |
| Payables control account equals open bills, every month | PASS | largest difference SAR 0.00 |
| VAT input and output accounts are cleared to VAT payable at every close | PASS | largest residue SAR 0.00 |
| No bank or cash account is overdrawn at the end of any day | PASS | lowest end-of-day balances all ≥ 0 |
| Inventory is never negative at a month end | PASS | all ≥ 0 |
| Stock ledger equals the sum of the stock layers (first in, first out) | PASS | ledger SAR 17,804,975.02, layers SAR 17,804,975.02 |
| No payment is dated before the invoice or bill it settles | PASS | 0 payments out of order |
| Every exported JSON file parses | PASS | 19 files read back |
| Line items, VAT and totals add up on every invoice, bill, receipt and credit note | PASS | 0 documents off by more than rounding |
| Every payment, credit note, contact and account reference resolves to an exported record | PASS | 0 unresolved references |
| Record IDs are unique | PASS | 43056 IDs, 0 duplicates |
| General ledger file: debits equal credits, and every transaction balances | PASS | debits SAR 5,321,059,080.54, credits SAR 5,321,059,080.54, unbalanced transactions 0 |
| Opening balances plus the general ledger file reproduce every account at every month end | PASS | largest difference SAR 0.00 |
| Opening receivables equal the go-live balances of the migrated invoices | PASS | opening SAR 42,490,488.41, migrated invoices SAR 42,490,488.41 |
| Categorised bank lines equal the bank accounts' movements in the ledger | PASS | largest difference SAR 0.00; 9 statement lines left uncategorised on purpose |
| No document is dated after the data end | PASS | 0 documents after 2026-11-19 |
| Printed trial balances: every month re-derived from the exported ledger ties, except the planted one | PASS | 46 months tested; months that differ: none |
| Covenants are set and the company is within them at its latest test date | PASS | 1 facility letter(s); leverage limit 3.00x |

## EH-07 Industrial Supplies

20 of 20 checks pass.

| Check | Result | Detail |
|---|---|---|
| Trial balance balances at every month end | PASS | largest imbalance SAR 0.00 |
| Receivables control account equals open invoices, every month | PASS | largest difference SAR 0.00 |
| Payables control account equals open bills, every month | PASS | largest difference SAR 0.00 |
| VAT input and output accounts are cleared to VAT payable at every close | PASS | largest residue SAR 0.00 |
| No bank or cash account is overdrawn at the end of any day | PASS | lowest end-of-day balances all ≥ 0 |
| Inventory is never negative at a month end | PASS | all ≥ 0 |
| Stock ledger equals the sum of the stock layers (first in, first out) | PASS | ledger SAR 25,787,601.29, layers SAR 25,787,601.29 |
| No payment is dated before the invoice or bill it settles | PASS | 0 payments out of order |
| Every exported JSON file parses | PASS | 19 files read back |
| Line items, VAT and totals add up on every invoice, bill, receipt and credit note | PASS | 0 documents off by more than rounding |
| Every payment, credit note, contact and account reference resolves to an exported record | PASS | 0 unresolved references |
| Record IDs are unique | PASS | 21823 IDs, 0 duplicates |
| General ledger file: debits equal credits, and every transaction balances | PASS | debits SAR 4,547,598,193.98, credits SAR 4,547,598,193.98, unbalanced transactions 0 |
| Opening balances plus the general ledger file reproduce every account at every month end | PASS | largest difference SAR 0.00 |
| Opening receivables equal the go-live balances of the migrated invoices | PASS | opening SAR 25,325,577.56, migrated invoices SAR 25,325,577.56 |
| Categorised bank lines equal the bank accounts' movements in the ledger | PASS | largest difference SAR 0.00; 8 statement lines left uncategorised on purpose |
| No document is dated after the data end | PASS | 0 documents after 2026-11-19 |
| S8: the new customer grows from under a fifth to about half of revenue (last 12 months) | PASS | top customer share Jun 2025 0.1601, Oct 2026 0.4943; effective number of customers 20.2613 → 3.9502 |
| Printed trial balances: every month re-derived from the exported ledger ties, except the planted one | PASS | 46 months tested; months that differ: none |
| Covenants are set and the company is within them at its latest test date | PASS | 1 facility letter(s); leverage limit 3.00x |

## EH-08 Food Distribution A

23 of 23 checks pass.

| Check | Result | Detail |
|---|---|---|
| Trial balance balances at every month end | PASS | largest imbalance SAR 0.00 |
| Receivables control account equals open invoices, every month | PASS | largest difference SAR 0.00 |
| Payables control account equals open bills, every month | PASS | largest difference SAR 0.00 |
| VAT input and output accounts are cleared to VAT payable at every close | PASS | largest residue SAR 0.00 |
| No bank or cash account is overdrawn at the end of any day | PASS | lowest end-of-day balances all ≥ 0 |
| Inventory is never negative at a month end | PASS | all ≥ 0 |
| Stock ledger equals the sum of the stock layers (first in, first out) | PASS | ledger SAR 33,425,111.16, layers SAR 33,425,111.16 |
| No payment is dated before the invoice or bill it settles | PASS | 0 payments out of order |
| Every exported JSON file parses | PASS | 20 files read back |
| Line items, VAT and totals add up on every invoice, bill, receipt and credit note | PASS | 0 documents off by more than rounding |
| Every payment, credit note, contact and account reference resolves to an exported record | PASS | 0 unresolved references |
| Record IDs are unique | PASS | 51921 IDs, 0 duplicates |
| General ledger file: debits equal credits, and every transaction balances | PASS | debits SAR 10,210,488,101.64, credits SAR 10,210,488,101.64, unbalanced transactions 0 |
| Opening balances plus the general ledger file reproduce every account at every month end | PASS | largest difference SAR 0.00 |
| Opening receivables equal the go-live balances of the migrated invoices | PASS | opening SAR 75,811,752.42, migrated invoices SAR 75,811,752.42 |
| Categorised bank lines equal the bank accounts' movements in the ledger | PASS | largest difference SAR 0.00; 8 statement lines left uncategorised on purpose |
| No document is dated after the data end | PASS | 0 documents after 2026-11-19 |
| S2: gross margin (LTM) falls after the October 2025 price change | PASS | Sep 2025 0.2305, Oct 2026 0.2056 |
| S2: about 23% of stock purchases are in euros | PASS | average monthly share 0.229 (range 0.05–0.37) |
| S2: 60% of items carry the purchase-price rise | PASS | 47 of 79 items |
| Printed trial balances: every month re-derived from the exported ledger ties, except the planted one | PASS | 46 months tested; months that differ: none |
| S11: revenue budgets too high in 7 of the last 8 quarters, by about 9% on average | PASS | 7 of 8 quarters above actual (2024Q4–2026Q3), average error +10.8% |
| Covenants are set and the company is within them at its latest test date | PASS | 1 facility letter(s); leverage limit 3.00x |

## EH-09 Food Distribution B

20 of 20 checks pass.

| Check | Result | Detail |
|---|---|---|
| Trial balance balances at every month end | PASS | largest imbalance SAR 0.00 |
| Receivables control account equals open invoices, every month | PASS | largest difference SAR 0.00 |
| Payables control account equals open bills, every month | PASS | largest difference SAR 0.00 |
| VAT input and output accounts are cleared to VAT payable at every close | PASS | largest residue SAR 0.00 |
| No bank or cash account is overdrawn at the end of any day | PASS | lowest end-of-day balances all ≥ 0 |
| Inventory is never negative at a month end | PASS | all ≥ 0 |
| Stock ledger equals the sum of the stock layers (first in, first out) | PASS | ledger SAR 22,554,429.52, layers SAR 22,554,429.52 |
| No payment is dated before the invoice or bill it settles | PASS | 0 payments out of order |
| Every exported JSON file parses | PASS | 20 files read back |
| Line items, VAT and totals add up on every invoice, bill, receipt and credit note | PASS | 0 documents off by more than rounding |
| Every payment, credit note, contact and account reference resolves to an exported record | PASS | 0 unresolved references |
| Record IDs are unique | PASS | 51752 IDs, 0 duplicates |
| General ledger file: debits equal credits, and every transaction balances | PASS | debits SAR 6,655,151,748.31, credits SAR 6,655,151,748.31, unbalanced transactions 0 |
| Opening balances plus the general ledger file reproduce every account at every month end | PASS | largest difference SAR 0.00 |
| Opening receivables equal the go-live balances of the migrated invoices | PASS | opening SAR 49,233,634.48, migrated invoices SAR 49,233,634.48 |
| Categorised bank lines equal the bank accounts' movements in the ledger | PASS | largest difference SAR 0.00; 6 statement lines left uncategorised on purpose |
| No document is dated after the data end | PASS | 0 documents after 2026-11-19 |
| S13: "Miscellaneous income" receives service revenue every month (true standard account: revenue) | PASS | booked in 47 months, SAR 15.5m since go-live, 1.6% of revenue |
| Printed trial balances: every month re-derived from the exported ledger ties, except the planted one | PASS | 46 months tested; months that differ: none |
| Covenants are set and the company is within them at its latest test date | PASS | 1 facility letter(s); leverage limit 3.00x |

## EH-14 Retail A (home and lifestyle)

21 of 21 checks pass.

| Check | Result | Detail |
|---|---|---|
| Trial balance balances at every month end | PASS | largest imbalance SAR 0.00 |
| Receivables control account equals open invoices, every month | PASS | largest difference SAR 0.00 |
| Payables control account equals open bills, every month | PASS | largest difference SAR 0.00 |
| VAT input and output accounts are cleared to VAT payable at every close | PASS | largest residue SAR 0.00 |
| No bank or cash account is overdrawn at the end of any day | PASS | lowest end-of-day balances all ≥ 0 |
| Inventory is never negative at a month end | PASS | all ≥ 0 |
| No payment is dated before the invoice or bill it settles | PASS | 0 payments out of order |
| Every exported JSON file parses | PASS | 21 files read back |
| Line items, VAT and totals add up on every invoice, bill, receipt and credit note | PASS | 0 documents off by more than rounding |
| Every payment, credit note, contact and account reference resolves to an exported record | PASS | 0 unresolved references |
| Record IDs are unique | PASS | 60177 IDs, 0 duplicates |
| General ledger file: debits equal credits, and every transaction balances | PASS | debits SAR 6,219,303,388.65, credits SAR 6,219,303,388.65, unbalanced transactions 0 |
| Opening balances plus the general ledger file reproduce every account at every month end | PASS | largest difference SAR 0.00 |
| Opening receivables equal the go-live balances of the migrated invoices | PASS | opening SAR 577,748.39, migrated invoices SAR 577,748.39 |
| Categorised bank lines equal the bank accounts' movements in the ledger | PASS | largest difference SAR 0.00; 9 statement lines left uncategorised on purpose |
| No document is dated after the data end | PASS | 0 documents after 2026-11-19 |
| S4: March 2026 sales about 11% below March 2025 (calendar only) | PASS | change -10.9% |
| S4: like-for-like growth is positive once the holiday effect is removed | PASS | March 2026 holiday-adjusted like-for-like 0.0385; raw -0.1376 |
| S4: return on invested capital falls with the nine new stores | PASS | ROIC (LTM, after Zakat) Dec 2024 0.1304, Oct 2026 0.0544 |
| Printed trial balances: every month re-derived from the exported ledger ties, except the planted one | PASS | 46 months tested; months that differ: none |
| Covenants are set and the company is within them at its latest test date | PASS | 1 facility letter(s); leverage limit 3.00x |

## EH-21 Facility Management A

22 of 22 checks pass.

| Check | Result | Detail |
|---|---|---|
| Trial balance balances at every month end | PASS | largest imbalance SAR 0.00 |
| Receivables control account equals open invoices, every month | PASS | largest difference SAR 0.00 |
| Payables control account equals open bills, every month | PASS | largest difference SAR 0.00 |
| VAT input and output accounts are cleared to VAT payable at every close | PASS | largest residue SAR 0.00 |
| No bank or cash account is overdrawn at the end of any day | PASS | lowest end-of-day balances all ≥ 0 |
| Inventory is never negative at a month end | PASS | all ≥ 0 |
| No payment is dated before the invoice or bill it settles | PASS | 0 payments out of order |
| Every exported JSON file parses | PASS | 17 files read back |
| Line items, VAT and totals add up on every invoice, bill, receipt and credit note | PASS | 0 documents off by more than rounding |
| Every payment, credit note, contact and account reference resolves to an exported record | PASS | 0 unresolved references |
| Record IDs are unique | PASS | 26087 IDs, 0 duplicates |
| General ledger file: debits equal credits, and every transaction balances | PASS | debits SAR 7,626,344,730.55, credits SAR 7,626,344,730.55, unbalanced transactions 0 |
| Opening balances plus the general ledger file reproduce every account at every month end | PASS | largest difference SAR 0.00 |
| Opening receivables equal the go-live balances of the migrated invoices | PASS | opening SAR 80,685,794.54, migrated invoices SAR 80,685,794.54 |
| Categorised bank lines equal the bank accounts' movements in the ledger | PASS | largest difference SAR 0.00; 8 statement lines left uncategorised on purpose |
| No document is dated after the data end | PASS | 0 documents after 2026-11-19 |
| S9: days late higher in January–October 2026 than a year earlier | PASS | average days late (3-month basis) 2025 46.6, 2026 59.1, change +12.5 |
| S7: bills bunch just below the SAR 50,000 approval limit after June 2025 | PASS | bills SAR 45,000–50,000 for each bill SAR 50,000–55,000: 1.3 before (248 vs 187), 3.1 after (355 vs 114) |
| S7: about 40 journals entered 30 or more days after their date, into months already closed | PASS | 40 such journals |
| S7: Friday postings by a rarely-posting user | PASS | 25 journals entered on Fridays by Saleh Al-Dosari (Accountant – Projects) |
| Printed trial balances: every month re-derived from the exported ledger ties, except the planted one | PASS | 46 months tested; months that differ: none |
| Covenants are set and the company is within them at its latest test date | PASS | 2 facility letter(s); leverage limit 3.00x |

## Group checks

| Check | Result | Detail |
|---|---|---|
| S5: every trading company's gross margin rises, the division's falls (last 12 months, Oct 2025 → Oct 2026) | PASS | EH-05 24.0% → 24.7% on revenue 364m → 394m; EH-06 26.2% → 27.4% on revenue 208m → 215m; EH-07 9.0% → 10.0% on revenue 156m → 248m; division 21.41% → 21.15% |
| S6: EH-05's receivable from EH-02 exceeds EH-02's payable to EH-05 by one unbooked invoice (31 Oct 2026) | PASS | EH-05 SAR 4.27m, EH-02 SAR 3.17m, difference SAR 1.10m |

## Change feed and acquisition data

- Change feed: 5454 events (5442 replaying activity from 1 November 2026, 12 live edits after the data end).
- Target statements: FY2023 balance sheet balances, cash flow ties, cash SAR 7.6m; FY2024 balance sheet balances, cash flow ties, cash SAR 22.1m; FY2025 balance sheet balances, cash flow ties, cash SAR 17.9m

