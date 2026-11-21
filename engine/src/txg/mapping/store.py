"""Versioned mappings (§8.5). Every version is kept; an override creates a new version (F-22, R16)."""
import re
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from txg.normalise.mapping_checks import proposal_checks

_COMPANY = re.compile(r"[A-Za-z0-9_-]{1,32}")


class VersionConflict(RuntimeError):
    """Another change wrote this version first; the caller re-reads and tries again."""


class MappingEntry(BaseModel):
    model_config = ConfigDict(frozen=True)
    account_id: str
    account_name: str
    zoho_type: str
    std_code: str
    confidence: str
    evidence: list[str]
    first_reading: str
    second_reading: str | None = None
    agreed: bool = True
    unreviewed: bool = False
    effect_sar: Decimal = Decimal(0)
    stand_in: bool = False
    reviewed_by: str | None = None
    review_reason: str | None = None
    findings: list[str] = Field(default_factory=list)


class MappingVersion(BaseModel):
    model_config = ConfigDict(frozen=True)
    company: str
    version: int
    created_at: datetime
    reason: str
    materiality: Decimal
    entries: dict[str, MappingEntry]
    findings: list[str] = Field(default_factory=list)  # check findings that fit no single entry

    def codes(self) -> dict[str, str]:
        return {a: e.std_code for a, e in self.entries.items()}

    def unreviewed_first(self) -> list[MappingEntry]:
        """The review page order (§9.10): unreviewed items first, largest effect first."""
        return sorted(self.entries.values(), key=lambda e: (not e.unreviewed, -e.effect_sar, e.account_id))


class MappingStore:
    def __init__(self, root: Path):
        self._root = root

    def _dir(self, company: str) -> Path:
        if not _COMPANY.fullmatch(company):
            raise ValueError(f"invalid company code: {company!r}")
        return self._root / company

    def _versions(self, company: str) -> list[int]:
        folder = self._dir(company)
        return sorted(int(p.stem[1:]) for p in folder.glob("v*.json")) if folder.is_dir() else []

    def get(self, company: str, version: int) -> MappingVersion:
        path = self._dir(company) / f"v{version}.json"
        return MappingVersion.model_validate_json(path.read_text(encoding="utf-8"))

    def latest(self, company: str) -> MappingVersion | None:
        versions = self._versions(company)
        return self.get(company, versions[-1]) if versions else None

    def save(self, company: str, entries: dict[str, MappingEntry], materiality: Decimal, reason: str,
             findings: list[str] | None = None) -> MappingVersion:
        number = (self._versions(company) or [0])[-1] + 1
        version = MappingVersion(company=company, version=number, created_at=datetime.now(UTC), reason=reason,
                                 materiality=materiality, entries=entries, findings=findings or [])
        folder = self._dir(company)
        folder.mkdir(parents=True, exist_ok=True)
        try:  # exclusive create: a writer that read an older state never overwrites a newer version
            with open(folder / f"v{number}.json", "x", encoding="utf-8") as f:
                f.write(version.model_dump_json(indent=1))
        except FileExistsError:
            raise VersionConflict(f"mapping version {number} for {company} already exists") from None
        return version

    def override(self, company: str, account_id: str, std_code: str, reason: str, person: str) -> MappingVersion:
        current = self.latest(company)
        if current is None or account_id not in current.entries:
            raise KeyError(f"no mapping for {account_id} in {company}")
        problems = proposal_checks(current.entries[account_id].zoho_type, std_code)
        if problems:
            raise ValueError(f"override rejected: {'; '.join(problems)}")
        changed = current.entries[account_id].model_copy(update={
            "std_code": std_code, "unreviewed": False, "reviewed_by": person, "review_reason": reason})
        entries = {**current.entries, account_id: changed}
        return self.save(company, entries, current.materiality, f"override {account_id}: {reason}")
