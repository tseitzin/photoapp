"""Query spans explain a request without describing the library.

Two things make DB tracing safe to point at a third party. Every value in this
codebase travels as a bind parameter, so db.statement is parameterised SQL and a
photo path stays out of it — asserted here rather than assumed, because one raw
f-string in a repository would silently break it. And a query is only recorded
when it sits under a request that is itself recorded, so the endpoints excluded
for volume stay excluded instead of reappearing as rootless SELECTs.
"""

from collections.abc import Iterator

import pytest
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core import telemetry
from app.core.sampling import SpansWorthKeeping
from app.core.telemetry import span
from app.models.photo import Photo

SECRET_PATH = "/Users/tim/Pictures/secret-folder/wedding.jpg"


@pytest.fixture
def traced_engine(db_engine: Engine) -> Iterator[InMemorySpanExporter]:
    """A provider with the real sampler, plus the real SQLAlchemy instrumentation."""
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

    saved_provider = trace._TRACER_PROVIDER  # noqa: SLF001
    exporter = InMemorySpanExporter()
    provider = TracerProvider(
        resource=telemetry.build_resource(Resource), sampler=SpansWorthKeeping()
    )
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace._TRACER_PROVIDER = provider  # noqa: SLF001

    SQLAlchemyInstrumentor().instrument(engine=db_engine, tracer_provider=provider)
    try:
        yield exporter
    finally:
        SQLAlchemyInstrumentor().uninstrument()
        trace._TRACER_PROVIDER = saved_provider  # noqa: SLF001


def _run_a_query(engine: Engine) -> None:
    with Session(engine) as session:
        session.execute(select(Photo).where(Photo.path == SECRET_PATH)).all()


def test_a_query_is_recorded_under_the_request_that_ran_it(
    traced_engine: InMemorySpanExporter, db_engine: Engine
) -> None:
    """The point of the whole exercise: a slow endpoint can be explained."""
    with span("GET /api/stats") as request_span:
        request_id = request_span.get_span_context().span_id
        _run_a_query(db_engine)

    queries = [s for s in traced_engine.get_finished_spans() if s.kind is SpanKind.CLIENT]

    assert queries, "the query produced no span"
    assert all(q.parent is not None and q.parent.span_id == request_id for q in queries)


def test_a_query_with_no_traced_request_above_it_is_dropped(
    traced_engine: InMemorySpanExporter, db_engine: Engine
) -> None:
    """A thumbnail request is excluded from tracing, so its queries must be too.

    Without this, one photo grid turns a deliberate exclusion into hundreds of
    rootless SELECT spans.
    """
    _run_a_query(db_engine)

    assert traced_engine.get_finished_spans() == ()


def test_a_query_filtering_on_a_path_does_not_put_the_path_on_the_span(
    traced_engine: InMemorySpanExporter, db_engine: Engine
) -> None:
    """Values are bound, so db.statement keeps the placeholder, not the folder."""
    with span("GET /api/photos"):
        _run_a_query(db_engine)

    leaked = [
        f"{key}={value}"
        for finished in traced_engine.get_finished_spans()
        for key, value in (finished.attributes or {}).items()
        if "secret-folder" in str(value)
    ]

    assert leaked == []


def test_a_query_span_carries_nothing_beyond_the_known_attributes(
    traced_engine: InMemorySpanExporter, db_engine: Engine
) -> None:
    """An allowlist rather than a search for today's secrets.

    Substring-matching the password cannot work here — the test database's
    password, user and name are all "aperture". More usefully, this pins the
    shape of what leaves the process: an upgrade that starts attaching a
    connection string or a bound-parameter dump fails this test instead of
    quietly shipping the library's paths to a third party.
    """
    permitted = {
        "db.name",
        "db.operation",
        "db.statement",
        "db.system",
        "db.user",
        "net.peer.name",
        "net.peer.port",
    }

    with span("GET /api/photos"):
        _run_a_query(db_engine)

    queries = [s for s in traced_engine.get_finished_spans() if s.kind is SpanKind.CLIENT]
    seen = {key for q in queries for key in (q.attributes or {})}

    assert queries
    assert seen <= permitted, f"unexpected attribute(s): {sorted(seen - permitted)}"


def test_a_background_scan_still_opens_its_own_trace(
    traced_engine: InMemorySpanExporter, db_engine: Engine
) -> None:
    """Only parentless *client* spans are dropped. A scan runs off a job runner
    with no request above it, and is the one place carrying aperture.* counts."""
    with span("scan"):
        _run_a_query(db_engine)

    kinds = {s.kind for s in traced_engine.get_finished_spans()}

    assert SpanKind.INTERNAL in kinds
    assert SpanKind.CLIENT in kinds


def test_setup_is_reversible_so_a_second_start_does_not_double_count(
    db_engine: Engine,
) -> None:
    """Engine listeners outlive the provider; shutdown must remove them.

    Counted by db.statement rather than by span kind: a pooled connection makes
    the accompanying "connect" span come and go, so counting client spans would
    be flaky for reasons that have nothing to do with double instrumentation.
    """
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

    saved_provider = trace._TRACER_PROVIDER  # noqa: SLF001
    exporter = InMemorySpanExporter()
    provider = TracerProvider(
        resource=telemetry.build_resource(Resource), sampler=SpansWorthKeeping()
    )
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace._TRACER_PROVIDER = provider  # noqa: SLF001

    try:
        for _ in range(2):
            SQLAlchemyInstrumentor().instrument(engine=db_engine, tracer_provider=provider)
            SQLAlchemyInstrumentor().uninstrument()
        SQLAlchemyInstrumentor().instrument(engine=db_engine, tracer_provider=provider)
        with span("GET /api/stats"):
            _run_a_query(db_engine)
        queries = [
            s for s in exporter.get_finished_spans() if "db.statement" in (s.attributes or {})
        ]
    finally:
        SQLAlchemyInstrumentor().uninstrument()
        trace._TRACER_PROVIDER = saved_provider  # noqa: SLF001

    assert len(queries) == 1


def test_a_cors_preflight_produces_no_spans_at_all(
    traced_engine: InMemorySpanExporter,
) -> None:
    """The browser sends OPTIONS before most mutations because the frontend is a
    separate origin. They do no work and answer no question — a week of ordinary
    use put ~2,700 of them in the dataset, about 9% of everything sent.

    'No spans at all' is the assertion that matters: dropping the server span
    alone would leave its ASGI `http send` child behind as a rootless fragment.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    app = FastAPI()

    @app.get("/api/photos/{photo_id}")
    def photo(photo_id: int) -> dict[str, int]:
        return {"id": photo_id}

    FastAPIInstrumentor.instrument_app(app)
    try:
        with TestClient(app) as client:
            client.options(
                "/api/photos/1",
                headers={
                    "Origin": "http://localhost:5173",
                    "Access-Control-Request-Method": "GET",
                },
            )
    finally:
        FastAPIInstrumentor.uninstrument_app(app)

    assert traced_engine.get_finished_spans() == ()


def test_a_real_request_is_still_recorded_in_full(
    traced_engine: InMemorySpanExporter,
) -> None:
    """The preflight rule must key on the method, not on the route — the same
    path serves a GET that is very much worth recording."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    app = FastAPI()

    @app.get("/api/photos/{photo_id}")
    def photo(photo_id: int) -> dict[str, int]:
        return {"id": photo_id}

    FastAPIInstrumentor.instrument_app(app)
    try:
        with TestClient(app) as client:
            client.get("/api/photos/1")
    finally:
        FastAPIInstrumentor.uninstrument_app(app)

    kinds = [s.kind for s in traced_engine.get_finished_spans()]

    assert SpanKind.SERVER in kinds
