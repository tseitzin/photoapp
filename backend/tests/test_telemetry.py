"""Tracing is opt-in, installs once, and never carries a filesystem path.

The redaction test is the one that makes pointing OTEL_EXPORTER_OTLP_ENDPOINT at
a third party safe: this app's spans describe a private photo library, and the
folder filter puts a real path in the query string of an ordinary request.
"""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.core import telemetry
from app.core.config import Settings, get_settings
from app.core.telemetry import SERVICE_NAME, add_attributes, redact_url_attributes, span


@pytest.fixture(autouse=True)
def _isolated_provider() -> Iterator[None]:
    """Put the global tracer provider back after every test.

    The SDK has no public reset, set_tracer_provider silently no-ops once set,
    and shutdown_telemetry deliberately does not unset it — so without this the
    tests are order-dependent.
    """
    saved_provider = trace._TRACER_PROVIDER  # noqa: SLF001
    saved_state = (telemetry._initialized, telemetry._provider)  # noqa: SLF001
    yield
    trace._TRACER_PROVIDER = saved_provider  # noqa: SLF001
    telemetry._initialized, telemetry._provider = saved_state  # noqa: SLF001


@pytest.fixture
def exported() -> InMemorySpanExporter:
    """A real SDK provider writing spans to memory."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider(resource=telemetry.build_resource(Resource))
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace._TRACER_PROVIDER = provider  # noqa: SLF001
    return exporter


@pytest.fixture
def tracing_off() -> None:
    trace._TRACER_PROVIDER = trace.NoOpTracerProvider()  # noqa: SLF001


def test_telemetry_is_disabled_by_default() -> None:
    """app = create_app() runs at import, including under pytest.

    If this ever defaults to True, every test run starts an exporter. Checked
    against the code default (_env_file=None) rather than the developer's .env.
    """
    defaults = Settings(_env_file=None)  # type: ignore[call-arg]

    assert defaults.telemetry_enabled is False
    assert defaults.telemetry_console_export is False


def test_the_test_suite_never_exports_spans() -> None:
    """Whatever backend/.env says — conftest forces it off before the app import."""
    assert get_settings().telemetry_enabled is False


def test_disabled_telemetry_installs_nothing() -> None:
    app = FastAPI()

    assert telemetry.setup_telemetry(app, enabled=False, console_export=False) is False
    assert app.user_middleware == []


def test_setting_up_telemetry_twice_installs_one_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """set_tracer_provider silently no-ops the second time, but
    instrument_app does not — it would double-count every request."""
    installs: list[FastAPI] = []

    class _Instrumentor:
        @staticmethod
        def instrument_app(app: FastAPI, **_: object) -> None:
            installs.append(app)

    monkeypatch.setattr(telemetry, "_initialized", False)
    monkeypatch.setattr(telemetry, "_provider", None)
    import opentelemetry.instrumentation.fastapi as fastapi_instrumentation

    monkeypatch.setattr(fastapi_instrumentation, "FastAPIInstrumentor", _Instrumentor)

    app = FastAPI()
    try:
        assert telemetry.setup_telemetry(app, enabled=True, console_export=True) is True
        assert telemetry.setup_telemetry(app, enabled=True, console_export=True) is True
    finally:
        telemetry.shutdown_telemetry()

    assert len(installs) == 1


def test_span_attributes_never_contain_a_filesystem_path(exported: InMemorySpanExporter) -> None:
    """A folder filter is an ordinary request carrying a real path."""
    scope = {"path": "/api/photos", "query_string": b"folder=/Users/tim/Pictures/secret-folder"}

    with span("request") as current:
        current.set_attribute("url.full", "http://x/api/photos?folder=/Users/tim/Pictures/secret")
        current.set_attribute("url.query", "folder=/Users/tim/Pictures/secret-folder")
        current.set_attribute("http.target", "/api/photos?folder=/Users/tim/Pictures/secret")
        redact_url_attributes(current, scope)

    attributes = exported.get_finished_spans()[0].attributes or {}

    assert attributes["url.full"] == "/api/photos"
    assert attributes["url.query"] == ""
    assert attributes["http.target"] == "/api/photos"
    assert not any("secret-folder" in str(value) for value in attributes.values())


def test_redaction_survives_a_request_through_the_instrumented_app(
    exported: InMemorySpanExporter,
) -> None:
    """End to end: the hook runs after the instrumentation sets its attributes,
    so whatever it wrote is overwritten rather than merely supplemented."""
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    app = FastAPI()

    @app.get("/api/photos")
    def photos(folder: str) -> dict[str, str]:
        return {"folder": folder}

    FastAPIInstrumentor.instrument_app(app, server_request_hook=redact_url_attributes)
    try:
        with TestClient(app) as client:
            client.get("/api/photos", params={"folder": "/Users/tim/Pictures/secret-folder"})
    finally:
        FastAPIInstrumentor.uninstrument_app(app)

    leaked = [
        f"{key}={value}"
        for finished in exported.get_finished_spans()
        for key, value in (finished.attributes or {}).items()
        if "secret-folder" in str(value)
    ]

    assert leaked == []


def test_a_path_is_refused_as_a_custom_span_attribute(exported: InMemorySpanExporter) -> None:
    """The rule is enforced, not just documented — no call site has to remember."""
    with span("organize") as current:
        add_attributes(current, src_path="/Users/tim/Pictures/a.jpg", moved=12)

    attributes = exported.get_finished_spans()[0].attributes or {}

    assert attributes.get("aperture.moved") == 12
    assert "aperture.src_path" not in attributes


def test_custom_attributes_are_namespaced_and_skip_nulls(exported: InMemorySpanExporter) -> None:
    with span("scan", scan_id=7, roots=2, absent=None):
        pass

    attributes = exported.get_finished_spans()[0].attributes or {}

    assert attributes["aperture.scan_id"] == 7
    assert attributes["aperture.roots"] == 2
    assert "aperture.absent" not in attributes


def test_a_failed_span_records_the_error_type_not_its_message(
    exported: InMemorySpanExporter,
) -> None:
    """OSError messages carry the filename they failed on."""
    with span("scan") as current:
        telemetry.record_failure(current, OSError("cannot read /Users/tim/Pictures/secret.jpg"))

    finished = exported.get_finished_spans()[0]

    assert (finished.attributes or {})["error.type"] == "OSError"
    assert "secret.jpg" not in str(finished.status.description)
    assert not any("secret.jpg" in str(value) for value in (finished.attributes or {}).values())


def test_the_resource_identifies_the_service_without_naming_the_machine(
    exported: InMemorySpanExporter,
) -> None:
    with span("scan"):
        pass

    resource = exported.get_finished_spans()[0].resource.attributes

    assert resource["service.name"] == SERVICE_NAME
    assert resource["deployment.environment"] == "local"
    # No username, home directory or hostname: the process and OS resource
    # detectors are opt-in and deliberately left off.
    assert not any(str(value).startswith("/Users/") for value in resource.values())


@pytest.mark.usefixtures("tracing_off")
def test_tracing_off_costs_nothing_and_records_nothing() -> None:
    """Services call span() unconditionally; with no provider it must be inert."""
    with span("scan", scan_id=1) as current:
        assert current.is_recording() is False
