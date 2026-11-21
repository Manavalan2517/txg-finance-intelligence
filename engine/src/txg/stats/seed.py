"""Simulation seeds (§12.6): seed = hash(company, period, KPI, configuration version), stored on the record."""
import hashlib

CONFIG_VERSION = "1"


def seed_for(company: str, period: str, kpi: str, config_version: str = CONFIG_VERSION) -> int:
    digest = hashlib.sha256(f"{company}|{period}|{kpi}|{config_version}".encode()).digest()
    return int.from_bytes(digest[:8], "big")
