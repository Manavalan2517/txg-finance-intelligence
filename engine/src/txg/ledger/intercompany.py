"""Intercompany matching (§12.17, R9, CK-09, CK-19). Code matches group companies by identifiers only (VAT, CR).
Unclear cases go to a reader (a model step; a labelled stand-in in simulation) and its verdict is recorded."""
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal

from txg.connector.base import Connector, OrgRef
from txg.ledger.subledger import open_by_contact
from txg.normalise.trial_balance import Finding

Resolver = Callable[[dict, OrgRef], tuple[bool, str]]
ZERO = Decimal(0)


@dataclass(frozen=True)
class ICPair:
    creditor: str      # the company that sold and holds the receivable
    debtor: str        # the company that bought and holds the payable
    receivable: Decimal
    payable: Decimal

    @property
    def difference(self) -> Decimal:
        return self.receivable - self.payable


def _identifiers(contact: dict) -> set[str]:
    ids = {contact.get("tax_reg_no") or ""}
    ids |= {f.get("value") or "" for f in contact.get("custom_fields") or [] if f.get("label") == "CR Number"}
    return {i for i in ids if i}


def classify_contacts(company: str, contacts: Sequence[dict], group: Sequence[OrgRef],
                      resolver: Resolver | None = None) -> tuple[dict[str, str], list[Finding]]:
    others = [o for o in group if o.company != company]
    by_id = {i: o.company for o in others for i in (o.vat_number, o.cr_number) if i}
    matches: dict[str, str] = {}
    findings: list[Finding] = []
    for contact in contacts:
        hit = next((by_id[i] for i in _identifiers(contact) if i in by_id), None)
        if hit:
            matches[contact["contact_id"]] = hit
            continue
        if resolver is None:
            continue
        for org in others:
            same, reason = resolver(contact, org)
            if same:
                matches[contact["contact_id"]] = org.company
                findings.append(Finding("CK-19", company, (
                    f"contact {contact['contact_id']} resolved to {org.company} by the reader ({reason}); its "
                    f"identifiers {sorted(_identifiers(contact))} differ from {org.company}'s "
                    f"{[org.vat_number, org.cr_number]}"), ZERO))
                break
    return matches, findings


def identify_group_contacts(conn: Connector, company: str, group: Sequence[OrgRef],
                            resolver: Resolver | None = None) -> tuple[dict[str, str], list[Finding]]:
    contacts = [r.data for r in conn.iter_records(company, "contacts")]
    return classify_contacts(company, contacts, group, resolver)


def match_intercompany(conn: Connector, companies: Sequence[str], month: str,
                       resolver: Resolver | None = None) -> tuple[list[ICPair], list[Finding]]:
    group = [o for o in conn.organisations() if o.company in companies]
    receivable: dict[tuple[str, str], Decimal] = {}
    payable: dict[tuple[str, str], Decimal] = {}
    findings: list[Finding] = []
    for company in companies:
        contacts, found = identify_group_contacts(conn, company, group, resolver)
        findings += found
        open_ar = open_by_contact(conn, company, "invoices", month)
        open_ap = open_by_contact(conn, company, "bills", month)
        for contact_id, other in contacts.items():
            receivable[(company, other)] = receivable.get((company, other), ZERO) + open_ar.get(contact_id, ZERO)
            payable[(company, other)] = payable.get((company, other), ZERO) + open_ap.get(contact_id, ZERO)
    pairs = []
    for creditor in companies:
        for debtor in companies:
            if creditor == debtor:
                continue
            r, p = receivable.get((creditor, debtor), ZERO), payable.get((debtor, creditor), ZERO)
            if r or p:
                pairs.append(ICPair(creditor, debtor, r, p))
    findings += [Finding("CK-09", p.creditor, f"intercompany mismatch with {p.debtor}", p.difference)
                 for p in pairs if p.difference]
    return pairs, findings
