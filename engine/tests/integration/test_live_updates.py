"""Live updates (§6.3, §16.8): a change posted by the client's replay script (`replay.py play --post URL`) is applied
at once, only that company's numbers are rebuilt, and every open screen hears about it over a server-sent event
stream, without a reload. The integrity flag on a change (IT-04) reaches only the CFO."""
import csv
import json
import queue
import socket
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient

from txg.api.app import create_app
from txg.api.live import ChangeBroker, LiveFeed, notice
from txg.api.service import EngineService
from txg.changes.processor import ApplyResult
from txg.connector.files import FileConnector
from txg.connector.overlay import OverlayConnector
from txg.record.store import EventLog

UPLOADS = Path(__file__).resolve().parents[3] / "data" / "txg-example-holding-uploads-2026-11-20"
TOKEN = "test-feed-token"
CEO = {"X-TXG-Role": "ceo"}


def _mapping(answer_key: Path, company: str) -> dict[str, str]:
    with open(answer_key / company / "chart_mapping.csv", encoding="utf-8", newline="") as f:
        return {r["account_id"]: r["standard_code"] for r in csv.DictReader(f)}


def _raw(seq: int) -> dict:
    with open(UPLOADS / "feed" / "changes.jsonl", encoding="utf-8") as f:
        return next(e for e in map(json.loads, f) if e["seq"] == seq)


def _build(zoho_root: Path, answer_key: Path, root: Path, token: str | None = TOKEN):
    if not UPLOADS.is_dir():
        pytest.skip("step-3 uploads not present")
    service = EngineService(OverlayConnector(FileConnector(zoho_root)),
                            {c: _mapping(answer_key, c) for c in ("EH-01", "EH-03")}, EventLog(root / "r.duckdb"),
                            uploads_root=UPLOADS)
    feed = LiveFeed(service, token=token)
    feed.gate_printed_months()
    return create_app(service, live=feed), service, feed


@pytest.fixture(scope="module")
def live(zoho_root: Path, answer_key: Path, tmp_path_factory):
    app, service, feed = _build(zoho_root, answer_key, tmp_path_factory.mktemp("live"))
    return TestClient(app), service, feed


def test_overlay_counts_versions_per_company(zoho_root: Path):
    from txg.connector.changefeed import parse_event
    conn = OverlayConnector(FileConnector(zoho_root))
    conn.apply_change(parse_event(_raw(5444)))
    assert conn.version_of("EH-01") == 1 and conn.version_of("EH-03") == 0 and conn.version == 1


def test_broker_delivers_each_message_to_every_subscriber_until_they_leave():
    broker, a, b = ChangeBroker(), [], []
    leave_a = broker.subscribe(a.append)
    broker.subscribe(b.append)
    broker.publish({"seq": 1})
    leave_a()
    broker.publish({"seq": 2})
    assert a == [{"seq": 1}] and b == [{"seq": 1}, {"seq": 2}]


def test_a_broken_subscriber_never_stops_the_others():
    broker, got = ChangeBroker(), []

    def broken(_msg: dict) -> None:
        raise RuntimeError("gone")

    broker.subscribe(broken)
    broker.subscribe(got.append)
    broker.publish({"seq": 1})
    assert got == [{"seq": 1}] and broker.count == 1


def test_the_integrity_flag_on_a_change_reaches_only_the_cfo():
    result = ApplyResult(5454, "EH-21", ["2026-09"], frozenset({"HL-3"}), after_close="edited despite the lock")
    assert "after_close" not in notice(result, "ceo")
    assert notice(result, "cfo")["after_close"] == "edited despite the lock"
    assert notice(result, "ceo") == {"seq": 5454, "company": "EH-21", "months": ["2026-09"], "kpis": ["HL-3"],
                                     "provisional": False, "period_status": ""}


@pytest.mark.slow
def test_start_up_ties_printed_months_and_holds_s12(live):
    client, service, _ = live
    assert service.gate.status_of("EH-03", "2026-08").status == "held"
    assert service.gate.status_of("EH-03", "2026-07").status == "tied"
    row = next(r for r in client.get("/group", params={"period": "2026-08"}, headers=CEO).json() if r["code"] == "EH-03")
    assert row["held"] is True


def test_a_change_needs_the_feed_token(live):
    client, _, _ = live
    assert client.post("/changes", json=_raw(5444)).status_code == 403
    assert client.post("/changes", params={"token": "wrong"}, json=_raw(5444)).status_code == 403


def test_the_change_feed_is_off_without_a_configured_token(zoho_root: Path, answer_key: Path, tmp_path: Path):
    app, _, _ = _build(zoho_root, answer_key, tmp_path, token=None)
    res = TestClient(app).post("/changes", params={"token": ""}, json=_raw(5444))
    assert res.status_code == 403 and res.json()["detail"] == "The change feed is not enabled"


def test_a_malformed_change_is_refused_without_internals(live):
    client, _, _ = live
    res = client.post("/changes", params={"token": TOKEN}, json={"seq": "x", "op": "create"})
    assert res.status_code == 422 and res.json()["detail"] == "Not a valid change event"


def test_a_change_for_an_unknown_company_is_404(live):
    client, _, _ = live
    raw = _raw(5444) | {"company": "EH-99"}
    assert client.post("/changes", params={"token": TOKEN}, json=raw).status_code == 404


@pytest.mark.slow
def test_the_corrected_upload_lifts_the_hold_and_is_published(live):
    client, _, feed = live
    got: list[dict] = []
    leave = feed.broker.subscribe(got.append)
    try:
        res = client.post("/changes", params={"token": TOKEN}, json=_raw(5450))
    finally:
        leave()
    assert res.status_code == 200 and res.json()["period_status"] == "tied"
    assert [m["seq"] for m in got] == [5450] and got[0]["company"] == "EH-03"
    row = next(r for r in client.get("/group", params={"period": "2026-08"}, headers=CEO).json() if r["code"] == "EH-03")
    assert row["held"] is False and row["kpis"]


@pytest.mark.slow
def test_an_invoice_change_rebuilds_only_that_company(live):
    client, service, _ = live
    before_03 = service.conn.version_of("EH-03")
    service.context("EH-03")
    old = service._context_key("EH-01")
    service.context("EH-01")
    res = client.post("/changes", params={"token": TOKEN}, json=_raw(5444))
    assert res.status_code == 200 and "RC-1" in res.json()["kpis"]
    assert service.conn.version_of("EH-03") == before_03
    assert old not in service._contexts  # the stale context is dropped, not kept forever
    assert service._context_key("EH-03") in service._contexts  # the other company keeps its cache


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.slow
def test_a_posted_change_reaches_an_open_stream(zoho_root: Path, answer_key: Path, tmp_path: Path):
    """End to end through a real server: the screen's stream hears the change the replay script posts."""
    app, _, feed = _build(zoho_root, answer_key, tmp_path)
    feed.heartbeat_seconds = 0.2
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    lines: queue.Queue[str] = queue.Queue()

    def listen() -> None:
        with httpx.stream("GET", f"{base}/events/stream", headers=CEO, timeout=30) as res:
            lines.put(f"status {res.status_code}")
            for line in res.iter_lines():
                lines.put(line)

    try:
        assert httpx.get(f"{base}/events/stream", timeout=5).status_code == 401
        threading.Thread(target=listen, daemon=True).start()
        assert lines.get(timeout=10) == "status 200"
        while feed.broker.count == 0:
            time.sleep(0.05)
        assert httpx.post(f"{base}/changes", params={"token": TOKEN}, json=_raw(5443), timeout=60).status_code == 200
        deadline, data = time.time() + 30, None
        while data is None and time.time() < deadline:
            line = lines.get(timeout=30)
            if line.startswith("data: "):
                data = json.loads(line[6:])
        assert data is not None and data["seq"] == 5443 and data["company"] == "EH-01"
        assert "after_close" not in data  # IT-04 is for the CFO's eyes only
    finally:
        server.should_exit = True
