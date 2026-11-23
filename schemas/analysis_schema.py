from enum import Enum
from pydantic import BaseModel, Field


class FindingCategory(str, Enum):
    METRIC_SUMMARY = "metric_summary"
    TREND = "trend"
    COMPARISON = "comparison"
    RANKING = "ranking"
    ANOMALY = "anomaly"
    ROOT_CAUSE = "root_cause"


class SupportingMetric(BaseModel):
    name: str = Field(description="Metric or segment name, e.g. 'Côte de Blaye revenue'.")
    value: float = Field(description="Exact numeric value.")
    unit: str = Field(default="USD", description="Unit such as 'USD', '%', 'orders', or 'units'.")


class BusinessFinding(BaseModel):
    finding_id: str = Field(
        description="Unique identifier, e.g. 'finding_1'."
    )
    category: FindingCategory = Field(
        description="Category of analytical insight."
    )
    headline: str = Field(
        description="Concise, concrete finding statement with exact numbers."
    )
    detail: str = Field(
        description="Supporting analytical explanation grounded in the query results."
    )
    supporting_metrics: list[SupportingMetric] = Field(
        default_factory=list,
        description="Exact numeric evidence backing this finding."
    )
    confidence: str = Field(
        default="high",
        description="Confidence level: 'high', 'medium', or 'low' based on data completeness."
    )


class AnalysisNarrative(BaseModel):
    """Schema returned by Gemini (strictly typed, no open dict fields)."""
    executive_summary: str = Field(
        description="Direct 2-3 sentence answer to the business question backed by exact numbers."
    )
    findings: list[BusinessFinding] = Field(
        default_factory=list,
        description="Structured analytical findings derived from deterministic tools and SQL data."
    )
    data_caveats: list[str] = Field(
        default_factory=list,
        description="Data limitations, truncation warnings, or correlation-vs-causation caveats."
    )


class AnalysisOutput(BaseModel):
    """Complete Agent 4 output combining LLM synthesis + deterministic Pandas tool outputs."""
    original_question: str = Field(
        description="Original business question asked by the user."
    )
    executive_summary: str = Field(
        description="Direct 2-3 sentence answer to the business question backed by exact numbers."
    )
    findings: list[BusinessFinding] = Field(
        default_factory=list,
        description="Structured analytical findings derived from deterministic tools and SQL data."
    )
    metric_calculations: dict = Field(
        default_factory=dict,
        description="Aggregated KPI summaries returned by analytics tools."
    )
    trend_analysis: dict = Field(
        default_factory=dict,
        description="Trend and growth rate calculations if time-series data was analyzed."
    )
    anomalies_detected: list[dict] = Field(
        default_factory=list,
        description="Statistical outliers or unusual shifts detected in the data."
    )
    root_cause_drivers: list[dict] = Field(
        default_factory=list,
        description="Ranked factors contributing to KPI changes (for root-cause queries)."
    )
    data_caveats: list[str] = Field(
        default_factory=list,
        description="Data limitations, truncation warnings, or correlation-vs-causation caveats."
    )
    is_successful: bool = Field(
        default=True,
        description="Whether analytical processing completed successfully."
    )