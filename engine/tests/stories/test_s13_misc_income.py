"""S13 (EH-09): "Miscellaneous income / إيرادات متنوعة" carries recurring service revenue. The two readings
disagree, code measures the effect, the higher-confidence reading is applied and the item is marked
"unreviewed" — and nothing waits for an approval (§15.4, F-21)."""
from pathlib import Path

import pytest

from txg.connector.files import FileConnector
from txg.mapping.runner import map_company
from txg.mapping.standins import first_reader, second_reader
from txg.mapping.store import MappingStore
from txg.modelsteps.client import ScriptedClient


@pytest.mark.slow
def test_s13_disagreement_marks_unreviewed(zoho_root: Path, tmp_path: Path):
    conn = FileConnector(zoho_root)
    version = map_company(conn, "EH-09", ScriptedClient(first_reader), ScriptedClient(second_reader),
                          MappingStore(tmp_path), as_of="2026-10")
    misc = [e for e in version.entries.values() if "miscellaneous income" in e.account_name.casefold()]
    assert len(misc) == 1
    entry = misc[0]
    assert entry.unreviewed and not entry.agreed
    assert entry.std_code == "4100"  # recurring-revenue reading had higher confidence
    assert {entry.first_reading, entry.second_reading} == {"4100", "4200"}
    assert entry.effect_sar >= version.materiality
    assert version.unreviewed_first()[0].account_id == entry.account_id  # tops the review list
