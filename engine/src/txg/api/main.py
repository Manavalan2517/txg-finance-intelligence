"""Run the results API for the prototype: `python -m txg.api.main` (port 8710).

Account mappings come from the mapping pipeline with the labelled stand-in readers (§9.9) until recorded model
answers exist. Only the prototype's own origin may call the API from a browser.

The books are served live: changes posted to /changes (the client's `replay.py play --post URL?token=…`) apply at
once. The feed is off unless TXG_FEED_TOKEN is set. TXG_RUNTIME and TXG_PORT let a test run use its own record."""
import logging
import os
from collections.abc import Sequence
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from txg.api.app import DEFAULT_PORT, create_app
from txg.api.live import LiveFeed
from txg.api.service import EngineService
from txg.connector.files import FileConnector
from txg.connector.overlay import OverlayConnector
from txg.mapping.runner import map_company
from txg.mapping.standins import first_reader, second_reader
from txg.mapping.store import MappingStore
from txg.modelsteps.client import ScriptedClient
from txg.record.store import EventLog

PROJECT = Path(__file__).resolve().parents[4]
DEFAULT_ZOHO = PROJECT / "data" / "example-holding-2026-11-20" / "data" / "zoho"
DEFAULT_RUNTIME = PROJECT / "engine" / "runtime"
DEFAULT_UPLOADS = PROJECT / "data" / "txg-example-holding-uploads-2026-11-20"
log = logging.getLogger("txg.api")
PROTOTYPE_ORIGINS = os.environ.get("TXG_PROTOTYPE_ORIGINS", "http://localhost:3000").split(",")


def build_app(zoho_root: Path, runtime: Path, companies: Sequence[str] | None = None, as_of: str = "2026-10") -> FastAPI:
    conn = FileConnector(zoho_root)
    store = MappingStore(runtime / "mappings")
    codes = list(companies) if companies else [o.company for o in conn.organisations()]
    mappings = {}
    for code in codes:
        version = store.latest(code) or map_company(conn, code, ScriptedClient(first_reader),
                                                    ScriptedClient(second_reader), store, as_of=as_of)
        mappings[code] = version.codes()
    uploads = DEFAULT_UPLOADS if DEFAULT_UPLOADS.is_dir() else None
    service = EngineService(OverlayConnector(conn), mappings, EventLog(runtime / "record.duckdb"),
                            uploads_root=uploads, store=store)
    live = LiveFeed(service, token=os.environ.get("TXG_FEED_TOKEN") or None) if uploads else None
    if live is not None:
        live.gate_printed_months()  # before the first request, so a held month is never served (B-14)
    app = create_app(service, live=live)
    app.state.service, app.state.live = service, live
    app.add_middleware(CORSMiddleware, allow_origins=PROTOTYPE_ORIGINS, allow_methods=["GET", "POST"],
                       allow_headers=["X-TXG-Role", "Content-Type"])
    return app


def warm_up(service: EngineService) -> None:
    """Build every company's latest closed month once, so the first page is not the slow one."""
    for company in list(service.mappings):
        period = service.closed_through(company)
        try:
            service.status_trend(company, period)
            service.simulated(company, period)
        except Exception:  # a warm-up failure must never stop the API; the request path reports it properly
            log.exception("warm-up failed for %s %s", company, period)


def main() -> None:
    import threading

    import uvicorn

    app = build_app(DEFAULT_ZOHO, Path(os.environ.get("TXG_RUNTIME", DEFAULT_RUNTIME)))
    threading.Thread(target=warm_up, args=(app.state.service,), daemon=True, name="warm-up").start()
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("TXG_PORT", DEFAULT_PORT)))


if __name__ == "__main__":
    main()
