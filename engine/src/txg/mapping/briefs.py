"""Mapping briefs (§9.3): only what the model needs for one account. No personal names (§6.6)."""
import re
from collections import Counter, defaultdict
from collections.abc import Mapping
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from txg.connector.base import Connector
from txg.normalise.trial_balance import TrialBalance

INSTRUCTIONS = (
    "You map one company account to the standard chart of accounts (Appendix C). Answer JSON only: "
    '{"account_id", "std_code", "confidence": "high"|"medium"|"low", "evidence": [..], "alternatives": [..], '
    '"note"}. Cite evidence from the brief. Never compute or invent numbers.'
)
_WINDOW = 24


class MappingBrief(BaseModel):
    company: str
    account_id: str
    code: str
    name: str
    zoho_type: str
    currency: str
    monthly_closing: list[str]
    months_with_activity: int
    months_total: int
    counterpart_types: dict[str, float]
    top_descriptions: list[str]


class MappingProposal(BaseModel):
    account_id: str
    std_code: str
    confidence: Literal["high", "medium", "low"]
    evidence: list[str] = Field(min_length=1)
    alternatives: list[str] = Field(default_factory=list)
    note: str | None = None


def render_brief(brief: MappingBrief) -> str:
    return f"{INSTRUCTIONS}\nBRIEF:\n{brief.model_dump_json()}"


def parse_brief(prompt: str) -> MappingBrief:
    body = prompt.split("BRIEF:\n", 1)[1].split("\n\nFINDING", 1)[0]
    return MappingBrief.model_validate_json(body)


def _personal_names(conn: Connector, company: str) -> list[str]:
    names = [r.data.get("contact_name", "") for r in conn.iter_records(company, "contacts")]
    names += [r.data.get("name", "") for r in conn.iter_records(company, "users")]
    return sorted({n for n in names if n and len(n) > 2}, key=len, reverse=True)


_HONORIFIC = re.compile(r"(\b(?:Mr|Mrs|Ms|Miss|Dr|Eng|Sheikh)\.?|السيد|السيدة|الأستاذ|المهندس|الشيخ)\s+[^\s/–-]+",
                        re.IGNORECASE)


def redact(text: str, names: list[str]) -> str:
    """Remove personal names (§6.6): known contacts and users, case-insensitively, and any honorific + name."""
    for n in names:
        text = re.sub(re.escape(n), "<name>", text, flags=re.IGNORECASE)
    return _HONORIFIC.sub(lambda m: f"{m.group(1)} <name>", text)


def _ledger_evidence(conn: Connector, company: str, types: Mapping[str, str], names: list[str]):
    """Per account: counterpart account types weighted by amount, and the most common descriptions."""
    by_txn: dict[str, list] = defaultdict(list)
    descriptions: dict[str, Counter] = defaultdict(Counter)
    for ln in conn.iter_ledger_lines(company):
        if ln.transaction_type != "opening_balance":
            by_txn[f"{ln.transaction_type}:{ln.transaction_id}"].append(ln)
        if ln.description:
            descriptions[ln.account_id][ln.description] += 1
    weights: dict[str, Counter] = defaultdict(Counter)
    for lines in by_txn.values():
        for ln in lines:
            for other in lines:
                if other.account_id != ln.account_id:
                    weights[ln.account_id][types.get(other.account_id, "unknown")] += float(other.debit + other.credit)
    shares = {}
    for acc, w in weights.items():
        total = sum(w.values()) or 1.0
        shares[acc] = {t: round(v / total, 2) for t, v in w.most_common(4)}
    top = {a: [redact(d, names) for d, _ in c.most_common(5)] for a, c in descriptions.items()}
    return shares, top


def build_briefs(conn: Connector, company: str, tbs: Mapping[str, TrialBalance], as_of: str) -> list[MappingBrief]:
    accounts = {r.data["account_id"]: r.data for r in conn.iter_records(company, "chartofaccounts")}
    types = {a: d.get("account_type", "") for a, d in accounts.items()}
    names = _personal_names(conn, company)
    shares, descriptions = _ledger_evidence(conn, company, types, names)
    months = [m for m in sorted(tbs) if m <= as_of]
    window = months[-_WINDOW:]
    briefs = []
    for acc_id, acc in accounts.items():
        active = [m for m in months if tbs[m].movements.get(acc_id)]
        if not any(tb.balances.get(acc_id) or tb.movements.get(acc_id) for tb in tbs.values()):  # CK-04: any month
            continue
        briefs.append(MappingBrief(
            company=company, account_id=acc_id, code=acc.get("account_code", ""),
            name=redact(acc.get("account_name", ""), names),
            zoho_type=types[acc_id], currency=acc.get("currency_code", "SAR"),
            monthly_closing=[str(tbs[m].balances.get(acc_id, Decimal(0))) for m in window],
            months_with_activity=len(active), months_total=len(months),
            counterpart_types=shares.get(acc_id, {}), top_descriptions=descriptions.get(acc_id, []),
        ))
    return briefs
