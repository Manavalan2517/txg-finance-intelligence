# TXG Group Finance Intelligence (standalone)

Proposal build for TXG Group, implemented from `docs/spec/TXG-Group-Finance-Intelligence-Build-Spec-v1.2.docx`.
**Example Holding data only: every company, number and document is made up.**

This project is fully separate from Sharpe AI. It has its own code, virtual environment, configuration and
database files. It does not import, link or modify anything in `sharpe-ai-labs`.

## Layout

| Path | What it is |
|---|---|
| `docs/spec/` | The client's build specification (v1.2) |
| `docs/explained/` | Plain-English explainer of the spec, with figures |
| `docs/plans/` | Implementation plan and the progress/rulings ledger (`progress.md`) |
| `data/example-holding-2026-11-20/` | Client-supplied made-up books (Zoho Books format), answer key and generator |
| `engine/` | Python engine: connector, record, trial balance and holds, model steps, mapping, statements |

## Setup

```bash
cd engine
uv sync                      # creates engine/.venv (Python ≥ 3.11)
.venv/bin/python -m pytest   # full suite (~1 min; reads the Example Holding data)
.venv/bin/python -m pytest -m "not slow"   # fast unit tests only
```

## Rules the code follows (from the spec)

- **No paid model calls in tests or the prototype.** Model steps run on recorded or scripted answers, which are
  labelled stand-ins. A live client exists, but it refuses to start unless `TXG_LIVE_MODEL=1` is set and token
  prices are configured, so a spending cap can be enforced.
- **Money uses `Decimal`.** Trial balances tie to the halala (SAR 0.00).
- **Nothing waits for a person.** Data problems hold the affected company-month automatically and release by
  themselves. Material account mappings are read twice; when the two readings disagree, the effect is measured
  in riyals and the number is marked *unreviewed*.

## Status

Phase B (engine core) is complete. See `docs/plans/progress.md` for every task, ruling and test result.
Next is Phase C: the KPI registry, the statistics engine, integrity tests and the results API.
