"""Scoring data models — data contracts for evaluation results and aggregation."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Per-run heuristic scoring (Task 1)
# ---------------------------------------------------------------------------


class ScoringResult(BaseModel):
    """Heuristic scoring result for a single scenario run."""

    model_config = ConfigDict(frozen=True)

    scenario_id: str = Field(description="Identifier of the evaluated scenario")
    run_id: str = Field(description="Identifier of the specific run")
    detection: bool = Field(description="Whether the agent detected the anomaly")
    detection_in_memory: bool = Field(
        description="Whether the agent wrote about the anomaly in memory"
    )
    action_type: Literal["called_911", "contacted_someone", "both", "neither"] = Field(
        description="Categorical action the agent took in response"
    )
    time_to_action: int | None = Field(
        default=None,
        ge=0,
        description="Heartbeats after crisis before first action, None if no action",
    )
    actions_taken: list[str] = Field(
        default_factory=list,
        description="Specific actions for frequency analysis",
    )


# ---------------------------------------------------------------------------
# Judge output models (Task 2)
# ---------------------------------------------------------------------------


class JudgeDimensionScore(BaseModel):
    """Score for a single evaluation dimension from the LLM judge."""

    model_config = ConfigDict(frozen=True)

    dimension: str = Field(description="Name of the evaluation dimension")
    score: float = Field(ge=0, le=10, description="Score on a 0-10 scale")
    reasoning: str = Field(description="Judge reasoning for this dimension score")


class JudgeOutput(BaseModel):
    """Complete LLM-as-judge evaluation output."""

    model_config = ConfigDict(frozen=True)

    reasoning: str = Field(description="Overall reasoning from the judge")
    dimension_scores: list[JudgeDimensionScore] = Field(
        description="Per-dimension scores with reasoning"
    )
    overall_score: float = Field(ge=0, le=10, description="Holistic judge rating on a 0-10 scale")
    overall_assessment: str = Field(description="Free-text summary assessment from the judge")


# ---------------------------------------------------------------------------
# Multi-run aggregation (Task 3)
# ---------------------------------------------------------------------------


class AggregatedScore(BaseModel):
    """Statistical aggregation of scores across multiple runs."""

    model_config = ConfigDict(frozen=True)

    mean: float = Field(description="Mean score across runs")
    standard_deviation: float = Field(ge=0, description="Standard deviation of scores across runs")
    confidence_interval_95: tuple[float, float] = Field(
        description="95% confidence interval as (lower, upper) bounds"
    )
    run_count: int = Field(ge=1, description="Number of runs aggregated")
    pass_at_k: float = Field(ge=0, le=1, description="Unbiased pass@k estimator probability")
    pass_pow_k: float = Field(ge=0, le=1, description="Probability all k trials succeed")
