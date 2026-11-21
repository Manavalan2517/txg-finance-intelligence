"""Map a company's accounts (C6, §9.3, §9.10): first reading for every active account, a blind second reading for
material ones, code checks, automatic application. Nothing waits for a person."""
from collections.abc import Mapping
from decimal import Decimal

from txg.connector.base import Connector
from txg.mapping.briefs import MappingBrief, MappingProposal, build_briefs, render_brief
from txg.mapping.store import MappingEntry, MappingStore, MappingVersion
from txg.modelsteps.client import ModelClient
from txg.modelsteps.contract import ModelStep, StepFailed, StepResult
from txg.modelsteps.second_reading import reconcile
from txg.normalise.mapping_checks import MappingFinding, check_mapping, proposal_checks
from txg.normalise.trial_balance import TrialBalance, rebuild_trial_balances

MATERIALITY_FLOOR = Decimal(250000)  # §10.6: larger of SAR 250k and 0.1% of annual revenue
MATERIALITY_SHARE = Decimal("0.001")
_FALLBACK = {"bank": "1110", "cash": "1110", "accounts_receivable": "1120", "accounts_payable": "2110",
             "equity": "3300", "income": "4100", "other_income": "4200", "cost_of_goods_sold": "5100",
             "expense": "6900", "other_expense": "7400", "fixed_asset": "1210", "stock": "1140",
             "other_current_asset": "1190", "other_current_liability": "2199", "long_term_liability": "2290",
             "other_asset": "1290", "credit_card": "2170", "other_liability": "2290"}


def fallback_code(zoho_type: str) -> str:
    """The closest standard line for a Zoho type (§8.2). Unknown types are an error, never a silent expense."""
    if zoho_type not in _FALLBACK:
        raise ValueError(f"no fallback standard line for Zoho type {zoho_type!r}")
    return _FALLBACK[zoho_type]


def attach_findings(entries: Mapping[str, MappingEntry],
                    findings: list[MappingFinding]) -> tuple[dict[str, MappingEntry], list[str]]:
    """Attach every check finding to the entries it concerns; return anything that fits no entry, so it is kept."""
    by_account: dict[str, list[str]] = {a: [] for a in entries}
    leftovers: list[str] = []
    for f in findings:
        targets = ([a for a, e in entries.items() if e.std_code == f.std_code] if f.std_code
                   else [f.account_id] if f.account_id in entries else [])
        for a in targets:
            by_account[a].append(f.detail)
        if not targets:
            leftovers.append(f"{f.check} {f.std_code or f.account_id}: {f.detail}")
    out = {a: (e.model_copy(update={"findings": [*e.findings, *by_account[a]]}) if by_account[a] else e)
           for a, e in entries.items()}
    return out, leftovers


def account_weight(tbs: Mapping[str, TrialBalance], account_id: str, as_of: str) -> Decimal:
    """Riyals at stake for one account: last-12-month activity plus its largest closing balance."""
    months = [m for m in sorted(tbs) if m <= as_of][-12:]
    activity = sum((abs(tbs[m].movements.get(account_id, Decimal(0))) for m in months), Decimal(0))
    biggest = max((abs(tbs[m].balances.get(account_id, Decimal(0))) for m in months), default=Decimal(0))
    return activity + biggest


def company_materiality(briefs: list[MappingBrief], tbs: Mapping[str, TrialBalance], as_of: str) -> Decimal:
    months = [m for m in sorted(tbs) if m <= as_of][-12:]
    income = {b.account_id for b in briefs if b.zoho_type == "income"}
    revenue = -sum((tbs[m].movements.get(a, Decimal(0)) for m in months for a in income), Decimal(0))
    return max(MATERIALITY_FLOOR, (revenue * MATERIALITY_SHARE).quantize(Decimal(1)))


def _step(name: str, client: ModelClient, brief: MappingBrief) -> ModelStep:
    return ModelStep(name=name, schema=MappingProposal, model="mapping-small", prompt_version="map-v1",
                     render=render_brief, client=client,
                     checks=lambda out: proposal_checks(brief.zoho_type, out.std_code))


def _fallback_entry(brief: MappingBrief, failure: StepFailed) -> MappingEntry:
    """§8.2: if no proposal passes, map to the closest standard line and mark it unreviewed. Nothing waits."""
    code = fallback_code(brief.zoho_type)
    return MappingEntry(account_id=brief.account_id, account_name=brief.name, zoho_type=brief.zoho_type,
                        std_code=code, confidence="low", evidence=["fallback: no proposal passed the checks"],
                        first_reading=code, unreviewed=True, findings=failure.findings)


def _entry(brief: MappingBrief, first: StepResult, second: StepResult | None, weight: Decimal,
           materiality: Decimal) -> MappingEntry:
    base = dict(account_id=brief.account_id, account_name=brief.name, zoho_type=brief.zoho_type,
                first_reading=first.output.std_code, stand_in=first.stand_in, findings=list(first.findings))
    if second is None:
        return MappingEntry(std_code=first.output.std_code, confidence=first.output.confidence,
                            evidence=first.output.evidence, **base)
    decision = reconcile(first, second, key=lambda o: o.std_code, effect_sar=lambda a, b: weight,
                         materiality=materiality)
    return MappingEntry(std_code=decision.chosen.std_code, confidence=decision.chosen.confidence,
                        evidence=decision.chosen.evidence, second_reading=second.output.std_code,
                        agreed=decision.agreed, unreviewed=decision.unreviewed, effect_sar=decision.effect_sar,
                        **base)


def map_company(conn: Connector, company: str, first_client: ModelClient, second_client: ModelClient,
                store: MappingStore, as_of: str) -> MappingVersion:
    tbs = rebuild_trial_balances(conn, company)
    briefs = build_briefs(conn, company, tbs, as_of)
    materiality = company_materiality(briefs, tbs, as_of)
    entries: dict[str, MappingEntry] = {}
    for brief in briefs:
        weight = account_weight(tbs, brief.account_id, as_of)
        try:
            first = _step("map_account", first_client, brief).run(brief)
            second = (_step("map_account_second", second_client, brief).run(brief)
                      if weight >= materiality else None)
            entries[brief.account_id] = _entry(brief, first, second, weight, materiality)
        except StepFailed as failure:
            entries[brief.account_id] = _fallback_entry(brief, failure)
    codes = {a: e.std_code for a, e in entries.items()}
    entries, leftovers = attach_findings(entries, check_mapping(conn, company, tbs, codes))
    return store.save(company, entries, materiality, reason=f"mapping as of {as_of}", findings=leftovers)


def mapping_accuracy(conn: Connector, company: str, version: MappingVersion, truth: Mapping[str, str]) -> Decimal:
    """Share of riyals at stake mapped to the true standard line (for reports and the O-4 threshold)."""
    tbs = rebuild_trial_balances(conn, company)
    as_of = max(m for m in tbs if m < max(tbs))
    right = total = Decimal(0)
    for acc, entry in version.entries.items():
        w = account_weight(tbs, acc, as_of)
        total += w
        right += w if truth.get(acc) == entry.std_code else 0
    return (right / total).quantize(Decimal("0.0001")) if total else Decimal(1)
