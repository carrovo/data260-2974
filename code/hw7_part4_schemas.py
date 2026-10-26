from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Part4StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        allow_inf_nan=False,
    )


class WeeklyRideRow(Part4StrictModel):
    week: str
    target_rides: int
    target_minutes: float


class Part4AdvisorResult(Part4StrictModel):
    recommendation: Literal[
        "Buy Monthly Membership",
        "Pay Per Ride/Minute",
    ]
    membership_cost: float
    pay_per_use_cost: float
    dollar_savings: float
    target_ride_count: int
    target_minutes: float
    average_target_minutes: float
    classic_target_count: int
    ebike_target_count: int
    weekly_table: list[WeeklyRideRow]
    assumptions: list[str]
    official_source_url: str
    citations: list[str]


class Part4TimelineItem(Part4StrictModel):
    action: str
    tool: str
    inputs: dict[str, Any]
    success: bool
    source: str | None = None
    latency_ms: float
    observation: dict[str, Any]


class Part4Metrics(Part4StrictModel):
    model_calls: int
    tool_calls: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    latency_ms: float


class Part4UploadSummary(Part4StrictModel):
    bytes: int
    rows: int
    target_rows: int


class Part4AnalyzeResponse(Part4StrictModel):
    result: Part4AdvisorResult
    timeline: list[Part4TimelineItem]
    verification: dict[str, Any]
    metrics: Part4Metrics
    stop_reason: str
    errors: list[str]
    upload: Part4UploadSummary
    framework: str
    final_response_diagnostics: dict[str, Any]
    message_trace: list[dict[str, Any]]
    model_configuration: dict[str, Any] = Field(alias="model_config")
