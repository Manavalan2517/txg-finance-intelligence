"""Results API (C15, §16.2, Appendix D.1). Every screen renders from here. The integrity page is CFO only and every
view is logged (§6.6). A held company-month is never published (B-14). Errors never leak internals."""
import asyncio
import json
import logging
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from txg.api import screens
from txg.api.live import LiveFeed, for_role, notice
from txg.api.service import EngineService, OverrideRejected
from txg.kpi.registry import load_registry
from txg.ledger.chart import load_standard_chart

log = logging.getLogger("txg.api")
ROLES = {"ceo", "cfo", "subsidiary_cfo", "reviewer"}
REVIEW_ROLES = {"cfo", "reviewer"}
PERIOD = r"^\d{4}-(0[1-9]|1[0-2])$"
SIMULATED_NAMES = {"HL-2": "Chance of hitting budget", "HL-7": "Liquidity low point"}
DEFAULT_PORT = 8710  # own port; nothing shared with any other application


class CompanyOut(BaseModel):
    code: str
    name: str
    currency: str


class KpiOut(BaseModel):
    company: str
    period: str
    kpi_id: str
    name: str
    value: str | None
    unit: str
    state: str
    provisional: bool
    depends_on_held_months: list[str] = []  # 12-month figures that include a held month
    status: str = "needs_data"
    trend: str | None = None


class GroupRow(BaseModel):
    code: str
    name: str
    held: bool
    reason: str | None = None
    kpis: list[KpiOut]


class OverrideIn(BaseModel):
    std_code: str = Field(pattern=r"^\d{4}$")
    reason: str = Field(min_length=3, max_length=500)


def _role(x_txg_role: Annotated[str | None, Header()] = None) -> str:
    """Prototype role header; production uses the identity provider and role-based access (§6.6)."""
    if x_txg_role not in ROLES:
        raise HTTPException(status_code=401, detail="A role is required")
    return x_txg_role


def _offer(q: asyncio.Queue, message: dict) -> None:
    """Queue a notice for one stream; a stream that has fallen far behind loses its oldest notice (any one notice
    makes the screen refresh, so nothing is missed on screen)."""
    if q.full():
        q.get_nowait()
    q.put_nowait(message)


def create_app(service: EngineService, live: LiveFeed | None = None) -> FastAPI:
    app = FastAPI(title="TXG Group Finance Intelligence — Example Holding, made-up data")

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error on %s", request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Something went wrong; it has been logged."})

    def _known(code: str) -> None:
        if not service.knows(code):
            raise HTTPException(status_code=404, detail=f"Unknown company {code}")

    @app.get("/companies", response_model=list[CompanyOut])
    def companies(x_txg_role: Annotated[str | None, Header()] = None):
        _role(x_txg_role)
        return [CompanyOut(code=o.company, name=o.name, currency=o.currency) for o in service.companies()]

    def _held(code: str, period: str) -> dict | None:
        status = service.gate.status_of(code, period)
        if status.status != "held":
            return None
        return {"held": True, "reason": status.reason, "last_good_month": service.gate.last_good_month(code, before=period)}

    def _company_kpis(code: str, period: str) -> list[KpiOut]:
        if (held_detail := _held(code, period)) is not None:
            raise HTTPException(status_code=409, detail=held_detail)
        names, provisional = load_registry(), period > service.closed_through(code)
        window = service.context(code).window(period, 12) or []
        held = [m for m in window if m != period and service.gate.status_of(code, m).status == "held"]
        st = service.status_trend(code, period)
        return [KpiOut(company=v.company, period=v.period, kpi_id=v.kpi_id, name=names[v.kpi_id].name,
                       value=None if v.value is None else str(v.value), unit=v.unit, state=v.state,
                       provisional=provisional, depends_on_held_months=held, status=st[v.kpi_id][0],
                       trend=st[v.kpi_id][1]) for v in service.kpis(code, period)] + [
            KpiOut(company=v.company, period=v.period, kpi_id=v.kpi_id, name=SIMULATED_NAMES[v.kpi_id],
                   value=str(v.value), unit=v.unit, state=v.state, provisional=provisional,
                   depends_on_held_months=held, status=status) for v, status in service.simulated(code, period)]

    @app.get("/companies/{code}/kpis", response_model=list[KpiOut])
    def kpis(code: str, period: Annotated[str, Query(pattern=PERIOD)],
             x_txg_role: Annotated[str | None, Header()] = None):
        _role(x_txg_role)
        _known(code)
        return _company_kpis(code, period)

    @app.get("/group", response_model=list[GroupRow])
    def group(period: Annotated[str, Query(pattern=PERIOD)], x_txg_role: Annotated[str | None, Header()] = None):
        """The heat-grid (§16.3): every company's headline pairs for one month; a held month shows as held."""
        _role(x_txg_role)
        rows = []
        for org in service.companies():
            held_detail = _held(org.company, period)
            values = [] if held_detail else [k for k in _company_kpis(org.company, period)
                                             if k.kpi_id in screens.HEADLINE]
            rows.append(GroupRow(code=org.company, name=org.name, held=held_detail is not None,
                                 reason=(held_detail or {}).get("reason"), kpis=values))
        return rows

    @app.get("/companies/{code}/series/{kpi_id}")
    def series(code: str, kpi_id: str, period: Annotated[str, Query(pattern=PERIOD)],
               x_txg_role: Annotated[str | None, Header()] = None):
        _role(x_txg_role)
        _known(code)
        if kpi_id not in load_registry():
            raise HTTPException(status_code=404, detail=f"Unknown measure {kpi_id}")
        if (held_detail := _held(code, period)) is not None:
            raise HTTPException(status_code=409, detail=held_detail)
        return screens.series(service, code, kpi_id, period)

    @app.get("/companies/{code}/cash13")
    def cash13(code: str, period: Annotated[str, Query(pattern=PERIOD)],
               x_txg_role: Annotated[str | None, Header()] = None):
        _role(x_txg_role)
        _known(code)
        if (held_detail := _held(code, period)) is not None:
            raise HTTPException(status_code=409, detail=held_detail)
        body = screens.cash13(service, code, period)
        if body is None:
            raise HTTPException(status_code=404, detail="The 13-week forecast runs for the latest closed month of "
                                                        "companies with facility terms")
        return body

    @app.get("/companies/{code}/receivables")
    def receivables(code: str, period: Annotated[str, Query(pattern=PERIOD)],
                    x_txg_role: Annotated[str | None, Header()] = None):
        _role(x_txg_role)
        _known(code)
        if (held_detail := _held(code, period)) is not None:
            raise HTTPException(status_code=409, detail=held_detail)
        return screens.receivables(service, code, period)

    @app.get("/companies/{code}/mappings")
    def mappings(code: str, x_txg_role: Annotated[str | None, Header()] = None):
        if _role(x_txg_role) not in REVIEW_ROLES:
            raise HTTPException(status_code=403, detail="The review page is for reviewers and the CFO")
        _known(code)
        try:
            return screens.mappings(service, code)
        except LookupError:
            raise HTTPException(status_code=404, detail="No mapping versions for this company") from None

    @app.post("/companies/{code}/mappings/{account_id}")
    def override(code: str, account_id: str, body: OverrideIn, x_txg_role: Annotated[str | None, Header()] = None):
        role = _role(x_txg_role)
        if role not in REVIEW_ROLES:
            raise HTTPException(status_code=403, detail="Only reviewers and the CFO can change a mapping")
        _known(code)
        try:
            version = service.override_mapping(code, account_id, body.std_code, body.reason, person=role)
        except KeyError:
            raise HTTPException(status_code=404, detail="Unknown account for this company") from None
        except OverrideRejected as e:
            raise HTTPException(status_code=422, detail=str(e)) from None
        except LookupError:
            raise HTTPException(status_code=404, detail="No mapping versions for this company") from None
        return {"company": code, "version": version.version, "entry": version.entries[account_id].model_dump(mode="json")}

    @app.get("/standard-chart")
    def standard_chart(x_txg_role: Annotated[str | None, Header()] = None):
        """The standard chart of accounts (Appendix C), for the review page's override choices."""
        _role(x_txg_role)
        return [{"code": a.code, "name": a.name, "class": a.cls} for a in load_standard_chart().values()]

    @app.get("/acquisition")
    def acquisition(x_txg_role: Annotated[str | None, Header()] = None):
        _role(x_txg_role)
        if service.uploads is None or not (service.uploads / "acquisition").is_dir():
            raise HTTPException(status_code=404, detail="No acquisition data room")
        return screens.acquisition(service.uploads)

    @app.get("/companies/{code}/integrity")
    def integrity(code: str, x_txg_role: Annotated[str | None, Header()] = None):
        role = _role(x_txg_role)
        _known(code)
        if role != "cfo":
            raise HTTPException(status_code=403, detail="The integrity page is for the CFO only")
        return screens.integrity(service, code, role)

    @app.post("/changes")
    async def change(request: Request, token: Annotated[str | None, Query(max_length=200)] = None):
        """The change feed's intake (§15.6): `replay.py play --post http://127.0.0.1:8710/changes?token=…`."""
        if live is None or not live.token:
            raise HTTPException(status_code=403, detail="The change feed is not enabled")
        if not live.accepts(token):
            log.warning("refused a change with a bad feed token from %s", request.client.host if request.client else "?")
            raise HTTPException(status_code=403, detail="Wrong feed token")
        from txg.connector.changefeed import parse_event
        try:
            event = parse_event(await request.json())
        except (KeyError, ValueError, TypeError, AttributeError):
            raise HTTPException(status_code=422, detail="Not a valid change event") from None
        if not service.knows(event.org):
            raise HTTPException(status_code=404, detail=f"Unknown company {event.org}")
        try:
            result = await run_in_threadpool(live.apply, event)
        except (ValueError, FileNotFoundError):
            log.warning("change %s refused", event.seq, exc_info=True)
            raise HTTPException(status_code=422, detail="The change could not be applied; it has been logged") from None
        return notice(result, "cfo")

    @app.get("/events/stream")
    async def stream(request: Request, x_txg_role: Annotated[str | None, Header()] = None):
        """Server-sent events: one `change` event per applied change, so open screens refresh themselves (§16.8)."""
        role = _role(x_txg_role)
        if live is None:
            raise HTTPException(status_code=404, detail="Live updates are not running")
        loop, q = asyncio.get_running_loop(), asyncio.Queue(maxsize=100)
        leave = live.broker.subscribe(lambda message: loop.call_soon_threadsafe(_offer, q, message))

        async def events():
            try:
                yield "retry: 3000\n: connected\n\n"
                while True:
                    try:
                        message = await asyncio.wait_for(q.get(), timeout=live.heartbeat_seconds)
                    except TimeoutError:
                        if await request.is_disconnected():
                            break
                        yield ": keep-alive\n\n"
                        continue
                    yield f"id: {message['seq']}\nevent: change\ndata: {json.dumps(for_role(message, role))}\n\n"
            finally:
                leave()

        return StreamingResponse(events(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})

    return app
