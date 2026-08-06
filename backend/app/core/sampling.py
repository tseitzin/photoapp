"""Sampling rule that keeps the excluded endpoints actually excluded.

The FastAPI instrumentation skips /health, /thumbnail and /preview because one
photo grid asks for hundreds of thumbnails and none of them are worth a span.
Those requests still query the database. Once queries are traced, a DB span with
no traced request above it starts a trace of its own — quietly turning "no spans
for thumbnails" into hundreds of rootless SELECTs, which is worse than what the
exclusion was written to prevent.

Dropping parentless client spans restores the intent: a query is worth recording
when it explains a request that is itself being recorded.
"""

from collections.abc import Sequence

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.sdk.trace.sampling import ALWAYS_ON, Decision, Sampler, SamplingResult
from opentelemetry.trace import Link, SpanKind
from opentelemetry.trace.span import TraceState
from opentelemetry.util.types import Attributes


class ParentedClientSpans(Sampler):
    """Record client spans only when something above them is already traced.

    Server and internal spans are unaffected: an HTTP request and a background
    scan are both legitimate trace roots.
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
        if kind is SpanKind.CLIENT and not parent.is_valid:
            return SamplingResult(Decision.DROP, attributes, trace_state)
        return ALWAYS_ON.should_sample(
            parent_context, trace_id, name, kind, attributes, links, trace_state
        )

    def get_description(self) -> str:
        return "ParentedClientSpans"
