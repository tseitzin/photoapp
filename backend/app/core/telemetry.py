"""Optional OpenTelemetry tracing — off unless TELEMETRY_ENABLED is set.

Vendor-neutral by design: the same spans reach Honeycomb or a local OTLP
backend by changing OTEL_EXPORTER_OTLP_ENDPOINT, with no code change.

**Telemetry never carries filesystem paths, filenames, usernames or machine
names.** Custom spans use ids, counts and outcomes only, and `add_attributes`
enforces that at runtime. Redacting the auto-instrumented URL attributes is
defence in depth for the attributes we do not write ourselves — a request like
`GET /api/photos?folder=/Users/.../Pictures/2019` would otherwise put a real
path, and its meaning, on a span bound for a third party.
"""

import logging
import os
from collections.abc import Iterator, MutableMapping
from contextlib import contextmanager
from typing import Any

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.trace import Span, Status, StatusCode, Tracer

from app.core.config import APP_VERSION

logger = logging.getLogger(__name__)

SERVICE_NAME = "aperture-api"
INSTRUMENTATION_SCOPE = "aperture"

# Both the current and legacy semantic-convention spellings: which pair the ASGI
# instrumentation emits depends on OTEL_SEMCONV_STABILITY_OPT_IN, and a leaked
# path is not something to leave to a default. The server_request_hook runs
# after the instrumentation sets these, so overwriting here is the final word.
_PATH_ONLY_ATTRIBUTES = ("url.full", "http.url", "http.target")
_CLEARED_ATTRIBUTES = ("url.query",)

# Thumbnails and previews are requested hundreds at a time by one grid page;
# health is polled. None of them are worth a span.
_DEFAULT_EXCLUDED_URLS = "health,thumbnail,preview"

_initialized = False
_provider: Any = None


def setup_telemetry(app: FastAPI, *, enabled: bool, console_export: bool) -> bool:
    """Install tracing on `app`. Returns whether tracing is now active.

    Called from create_app() rather than the lifespan hook: instrument_app adds
    middleware, and FastAPI forbids that once the app has started.
    """
    global _initialized, _provider

    if not enabled:
        return False
    if _initialized:
        # set_tracer_provider silently no-ops on a second call and
        # double-instrumenting the same app double-counts every request.
        return True

    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

    from app.core.sampling import SpansWorthKeeping

    os.environ.setdefault("OTEL_PYTHON_FASTAPI_EXCLUDED_URLS", _DEFAULT_EXCLUDED_URLS)

    provider = TracerProvider(resource=build_resource(Resource), sampler=SpansWorthKeeping())
    if console_export:
        # Console *instead of* OTLP, so instrumentation can be inspected without
        # sending anything anywhere.
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        destination = "console"
    else:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        # No endpoint argument: the SDK reads OTEL_EXPORTER_OTLP_ENDPOINT itself
        # and appends /v1/traces. Passing it through would skip that append and
        # silently post to the wrong URL.
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        destination = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")

    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app, server_request_hook=redact_url_attributes)
    instrument_database()

    _provider = provider
    _initialized = True
    logger.info("tracing enabled, exporting to %s", destination)
    return True


def instrument_database() -> None:
    """Add a span per SQL statement, nested under the request that ran it.

    Instruments the engine instance rather than patching create_engine: by the
    time create_app() reaches setup_telemetry it has already included the
    routers, which import the repositories, which import app.db.session — so the
    engine exists and a create_engine patch would come too late to see it.
    """
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

    from app.db.session import engine

    SQLAlchemyInstrumentor().instrument(engine=engine)


def shutdown_telemetry() -> None:
    """Flush buffered spans. BatchSpanProcessor drops them without this."""
    global _initialized, _provider

    if _initialized:
        # Engine event listeners outlive the provider, so a second setup in the
        # same process would otherwise stack a second span on every query.
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        SQLAlchemyInstrumentor().uninstrument()
    if _provider is not None:
        _provider.shutdown()
    _provider = None
    _initialized = False


def redact_url_attributes(span: Span | None, scope: MutableMapping[str, Any]) -> None:
    """Reduce the auto-instrumented URL attributes to the path alone."""
    if span is None or not span.is_recording():
        return
    path = str(scope.get("path") or "")
    for attribute in _PATH_ONLY_ATTRIBUTES:
        span.set_attribute(attribute, path)
    for attribute in _CLEARED_ATTRIBUTES:
        span.set_attribute(attribute, "")


def build_resource(resource_cls: Any) -> Any:
    # Resource.create runs only the env-var detector by default. The process and
    # OS detectors — which carry command lines and hostnames — are opt-in via
    # OTEL_EXPERIMENTAL_RESOURCE_DETECTORS, and deliberately not enabled.
    return resource_cls.create(
        {
            "service.name": SERVICE_NAME,
            "service.version": APP_VERSION,
            "deployment.environment": "local",
        }
    )


def tracer() -> Tracer:
    """A tracer that is a cheap no-op when tracing is disabled."""
    return trace.get_tracer(INSTRUMENTATION_SCOPE)


def add_attributes(span: Span, **attributes: object) -> None:
    """Attach `aperture.*` attributes, refusing anything that looks like a path.

    The runtime check makes "no paths in telemetry" an enforced invariant rather
    than a convention someone has to remember at every call site.
    """
    for key, value in attributes.items():
        if value is None:
            continue
        if isinstance(value, str) and (os.sep in value or value.startswith("~")):
            logger.warning("refusing to put a path-like value on a span: %s", key)
            continue
        span.set_attribute(f"aperture.{key}", value)  # type: ignore[arg-type]


def record_failure(current_span: Span, exc: BaseException) -> None:
    """Mark a span failed by exception *type* only.

    Deliberately not span.record_exception(): a traceback carries source paths,
    and an OSError's message carries the filename it failed on. The message
    belongs in the local log, which has the request id to correlate with.
    """
    current_span.set_status(Status(StatusCode.ERROR, type(exc).__name__))
    current_span.set_attribute("error.type", type(exc).__name__)


@contextmanager
def span(name: str, **attributes: object) -> Iterator[Span]:
    """Record a span, or do nothing measurable when tracing is off."""
    with tracer().start_as_current_span(name) as current:
        add_attributes(current, **attributes)
        yield current
