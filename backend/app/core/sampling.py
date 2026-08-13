"""What is worth recording, and what is just noise that happens to be traceable.

Three rules, each earned by something that actually polluted the data:

**A dropped span's children go with it.** Whatever the sampler refuses, the SDK
still makes current as a non-recording parent, so children are sampled
independently and would survive their own parent — arriving as rootless
fragments of a trace that was deliberately discarded.

**CORS preflights carry no information.** The frontend is a separate origin, so
the browser sends an `OPTIONS` before most mutations. They touch no database and
do no work, yet each produced a server span plus an ASGI `http send` child.
Measured over a week of ordinary use: ~2,700 spans, about 9% of everything sent,
none of it capable of answering a question.

**A query is worth recording when it explains a recorded request.** /health,
/thumbnail and /preview are excluded from HTTP tracing because one photo grid
asks for hundreds of thumbnails. Those requests still query the database, and a
DB span with no traced request above it starts a trace of its own — quietly
turning "no spans for thumbnails" into hundreds of rootless SELECTs, which is
worse than what the exclusion was written to prevent.
"""

from collections.abc import Sequence

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.sdk.trace.sampling import ALWAYS_ON, Decision, Sampler, SamplingResult
from opentelemetry.trace import Link, SpanKind
from opentelemetry.trace.span import TraceState
from opentelemetry.util.types import Attributes

# Both spellings: which one the ASGI instrumentation emits depends on
# OTEL_SEMCONV_STABILITY_OPT_IN, and this should not quietly stop working when
# that default flips.
_METHOD_KEYS = ("http.method", "http.request.method")


class SpansWorthKeeping(Sampler):
    """Drop preflights, orphans, and the children of anything already dropped.

    Server and internal spans are otherwise untouched: an HTTP request and a
    background scan are both legitimate trace roots.
    """

    def should_sample(
        self,
        parent_context: Context | None,
        trace_id: int,
        name: str,
        kind: SpanKind | None = None,
        attributes: Attributes = None,
        links: Sequence[Link] | None = None,
        trace_state: TraceState | None = None,
    ) -> SamplingResult:
        parent = trace.get_current_span(parent_context).get_span_context()

        # A child of a span that was refused is a fragment of a trace that no
        # longer exists. Checked first: it decides every descendant at once.
        if parent.is_valid and not parent.trace_flags.sampled:
            return SamplingResult(Decision.DROP, attributes, trace_state)

        if kind is SpanKind.SERVER and _is_preflight(attributes):
            return SamplingResult(Decision.DROP, attributes, trace_state)

        if kind is SpanKind.CLIENT and not parent.is_valid:
            return SamplingResult(Decision.DROP, attributes, trace_state)

        return ALWAYS_ON.should_sample(
            parent_context, trace_id, name, kind, attributes, links, trace_state
        )

    def get_description(self) -> str:
        return "SpansWorthKeeping"


def _is_preflight(attributes: Attributes) -> bool:
    values = attributes or {}
    return any(values.get(key) == "OPTIONS" for key in _METHOD_KEYS)
