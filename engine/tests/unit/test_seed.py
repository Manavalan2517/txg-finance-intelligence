"""Seeds (§12, B-10): every company, period and measure gets its own seed, derived from the key, so simulations are
reproducible and never share random draws across companies."""
from txg.stats.seed import seed_for


def test_the_same_key_gives_the_same_seed():
    assert seed_for("EH-01", "2026-10", "HL-7") == seed_for("EH-01", "2026-10", "HL-7")


def test_each_company_gets_its_own_seed():
    seeds = {seed_for(c, "2026-10", "HL-7") for c in ("EH-01", "EH-02", "EH-03", "EH-05", "EH-21")}
    assert len(seeds) == 5


def test_period_and_measure_change_the_seed():
    base = seed_for("EH-01", "2026-10", "HL-7")
    assert seed_for("EH-01", "2026-09", "HL-7") != base and seed_for("EH-01", "2026-10", "HL-2") != base
