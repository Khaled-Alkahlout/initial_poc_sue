"""HTTP contracts: observed results, provenance and unknown values stay separate."""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field

StageStatus = Literal[
    "pending",
    "running",
    "passed",
    "failed",
    "warning",
    "inconclusive",
    "skipped",
    "error",
]
Lifecycle = Literal["PENDING", "RUNNING", "COMPLETED", "FAILED"]
Mode = Literal["historical", "replay", "mock", "live_mock", "live"]
Condition = Literal["C1_query", "C2_schema", "C3_plan", "C4_stats"]
Outcome = Literal[
    "accepted",
    "not_faster",
    "mismatch",
    "safety_rejected",
    "inconclusive",
    "error",
    "unavailable",
]


class Stage(BaseModel):
    id: str
    label: str
    status: StageStatus
    note: str
    duration_ms: float | None = None
    origin: str = "historical"


class Benchmark(BaseModel):
    original_ms: float | None = None
    proposed_ms: float | None = None
    original_iqr_ms: float | None = None
    proposed_iqr_ms: float | None = None
    speedup: float | None = None
    reduction_percent: float | None = None
    repetitions: int | None = None
    status: StageStatus = "skipped"
    origin: str = "historical"


class ContextSection(BaseModel):
    id: str
    label: str
    state: Literal["available", "unavailable", "omitted", "redacted", "truncated"]
    text: str | None = None
    note: str


class Attempt(BaseModel):
    id: str
    run_id: str
    query_id: str
    candidate: str
    condition: str | None = None
    repetition: int | None = None
    model: str | None = None
    raw_verdict: str | None = None
    outcome: Outcome
    correctness: StageStatus
    original_sql: str | None = None
    proposed_sql: str | None = None
    explanation: str | None = None
    detail: str
    parameter_sets: int | None = None
    failing_parameter_sets: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    llm_seconds: float | None = None
    unchanged: bool | None = None
    stages: list[Stage]
    benchmark: Benchmark
    context: list[ContextSection] = Field(default_factory=list)
    raw_record: dict[str, Any] = Field(default_factory=dict)
    origin: str = "historical"


class RunSummary(BaseModel):
    id: str
    title: str
    mode: Mode
    lifecycle: Lifecycle
    created_at: str
    completed_at: str | None = None
    query_ids: list[str] = Field(default_factory=list)
    attempt_count: int = 0
    accepted_count: int = 0
    issue_count: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    model_requests: int | None = None
    source_id: str | None = None
    error: str | None = None


class RunDetail(RunSummary):
    attempts: list[Attempt] = Field(default_factory=list)
    stages: list[Stage] = Field(default_factory=list)
    selection: dict[str, Any] | None = None
    limitations: list[str] = Field(default_factory=list)


class QueryView(BaseModel):
    query_id: str
    sql: str | None
    calls: int | None
    mean_execution_time_ms: float | None
    total_execution_time_ms: float | None
    impact_ms: float | None
    impact_source: str | None
    rank: int | None
    status: Literal["eligible", "excluded", "deferred"]
    selected: bool
    reason_codes: list[str]
    source: str
    is_synthetic: bool
    window_id: str | None
    dialect: str
    analyzed: bool
    related_run_ids: list[str]
    analysis_count: int
    latest_outcome: Outcome | None = None


class QueryCollection(BaseModel):
    queries: list[QueryView]
    policy: dict[str, Any]


class QueryDetail(QueryView):
    runs: list[RunSummary]
    attempts: list[Attempt]


class Metric(BaseModel):
    id: str
    label: str
    value: float | None
    note: str
    origin: str


class ConditionStats(BaseModel):
    condition: str
    requests: int
    independent_queries: int
    accepted: int
    rejected: int
    inconclusive: int
    unchanged: int
    input_tokens: int | None
    output_tokens: int | None


class Overview(BaseModel):
    metrics: list[Metric]
    queries: list[QueryView]
    recent_runs: list[RunSummary]
    conditions: list[ConditionStats]
    warnings: list[str]


class TestRecord(BaseModel):
    id: str
    name: str
    component: str
    purpose: str
    expected: str | None = None
    actual: str | None = None
    status: StageStatus
    duration_ms: float | None = None
    error_classification: str | None = None
    executed_at: str | None = None
    run_id: str | None = None
    query_id: str | None = None
    origin: str
    detail: str
    attempt: Attempt | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TestCollection(BaseModel):
    tests: list[TestRecord]
    counts: dict[str, int]
    warnings: list[str]


class TestExecution(BaseModel):
    id: str
    suite: str
    lifecycle: Lifecycle
    created_at: str
    completed_at: str | None = None
    tests: list[TestRecord] = Field(default_factory=list)
    error: str | None = None


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class RunRequest(StrictInput):
    mode: Literal["replay", "mock", "live_mock", "live"] = "replay"
    query_id: str = Field(min_length=1, max_length=80)
    condition: Condition = "C2_schema"
    source_id: str | None = Field(default=None, max_length=100)
    confirm_sql: bool = False
    confirm_external_model: bool = False


class TestRequest(StrictInput):
    suite: Literal["selection", "routing", "mutations"]
    query_id: str = "top_products"
    confirm_sql: bool = False


class FeedbackInput(StrictInput):
    target_type: Literal["run", "test", "attempt"]
    target_id: str = Field(min_length=1, max_length=240)
    label: Literal["correct", "incorrect", "needs_review"]
    comment: str = Field(default="", max_length=2000)
    reviewer: str = Field(default="", max_length=80)


class Feedback(FeedbackInput):
    id: str
    created_at: str


class Capability(BaseModel):
    id: str
    label: str
    available: bool
    reason: str
    executes_sql: bool = False
    external_model: bool = False


class SystemStatus(BaseModel):
    api_status: str = "available"
    database_status: str = "not_checked"
    database_configured: bool
    model_configured: bool
    dependencies: dict[str, bool]
    fixtures: int
    historical_runs: int
    historical_evaluations: int
    filter_available: bool = True
    run_modes: list[Capability]
    test_suites: list[Capability]
    warnings: list[str]
    limitations: list[str]
