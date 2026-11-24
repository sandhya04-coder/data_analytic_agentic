from enum import Enum
from pydantic import BaseModel, Field

from typing import Literal

class ChartSpec(BaseModel):
    task_id: str = Field(..., description="Exact task_id from the executed SQL query to plot.")
    chart_type: Literal["bar", "grouped_bar", "line", "scatter", "heatmap", "treemap", "pareto"] = Field(
        ..., description="Best chart type for this specific question and data shape."
    )
    x_col: str = Field(..., description="Exact column name for the X-axis (or category/hierarchy root).")
    y_col: str = Field(..., description="Exact numeric column name for the Y-axis (or metric value).")
    color_col: str | None = Field(
        default=None,
        description="Optional exact column name for series grouping / color encoding (e.g., year or category).",
    )
    title: str = Field(..., description="Clear executive chart title.")
    subtitle: str = Field(default="", description="One-line analytical takeaway or axis context.")
class RecommendationPriority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class KPIHighlight(BaseModel):
    label: str = Field(description="Short KPI label, e.g. 'Total Q1 2018 Revenue' or 'QoQ Growth'.")
    value: str = Field(description="Formatted metric value, e.g. '$298,491.55' or '+64.3%'.")
    delta: str = Field(default="", description="Optional variance badge, e.g. '+$116,810.09 vs Q4 2017'.")
    sentiment: str = Field(default="neutral", description="'positive', 'negative', or 'neutral'.")


class DriverHighlight(BaseModel):
    segment: str = Field(description="Segment/entity name, e.g. 'Beverages • Western Europe'.")
    metric_value: str = Field(description="Primary metric or change formatted cleanly, e.g. '+$25,524.53 (+263.0%)'.")
    role: str = Field(description="'Growth Driver', 'Top Performer', 'Contraction Risk', or 'Outlier'.")
    takeaway: str = Field(description="One-line business interpretation.")


class Recommendation(BaseModel):
    recommendation_id: str = Field(description="Unique identifier, e.g. 'rec_1'.")
    title: str = Field(description="Short action-oriented recommendation title.")
    action: str = Field(description="Concrete, specific business action to take.")
    rationale: str = Field(description="Quantified evidence from the analysis supporting this recommendation.")
    priority: RecommendationPriority = Field(default=RecommendationPriority.MEDIUM)
    expected_impact: str = Field(description="Quantified or concrete expected business outcome.")


class ChartArtifact(BaseModel):
    task_id: str
    chart_type: str
    title: str
    html_path: str
    figure_json: str = ""


class ReportNarrative(BaseModel):
    """Strictly typed schema returned by Gemini for executive report synthesis."""
    report_title: str = Field(description="Crisp, boardroom-ready report title.")
    subtitle: str = Field(description="One-line scope & period subtitle, e.g. 'Period Comparison: Q4 2017 vs. Q1 2018 across 8 Categories & 9 Regions'.")
    headline_kpis: list[KPIHighlight] = Field(
        default_factory=list,
        description="3-4 punchy headline KPI cards summarizing the most important numbers and deltas."
    )
    business_summary: str = Field(
        description="2-3 sentence executive synthesis: bottom-line answer first, primary driver second, key risk third."
    )
    top_drivers: list[DriverHighlight] = Field(
        default_factory=list,
        description="3-6 ranked segment drivers, top performers, or contraction risks with exact numbers."
    )
    key_findings_summary: list[str] = Field(
        default_factory=list,
        description="4-5 sharp, bold-lead bullet takeaways with exact figures and percentages."
    )
    root_cause_section: str = Field(
        default="",
        description="Structured decomposition explaining positive vs. negative drivers if comparison/root-cause analysis was performed."
    )
    recommendations: list[Recommendation] = Field(
        default_factory=list,
        description="2-4 concrete, prioritized recommendations tied to specific segments and quantified figures."
    )
    supporting_evidence_notes: list[str] = Field(
        default_factory=list,
        description="Deduplicated data governance, SQL coverage, and methodological caveats."
    )
    follow_up_questions: list[str] = Field(
        default_factory=list,
        description="3 concrete analytical drill-down questions the user should ask next based on the anomalies, top drivers, or risks uncovered."
    )
    chart_specs: list[ChartSpec] = Field(default_factory=list)


class ExecutiveReport(BaseModel):
    original_question: str
    report_title: str
    subtitle: str = ""
    headline_kpis: list[KPIHighlight] = Field(default_factory=list)
    business_summary: str
    top_drivers: list[DriverHighlight] = Field(default_factory=list)
    key_findings_summary: list[str] = Field(default_factory=list)
    root_cause_section: str = ""
    recommendations: list[Recommendation] = Field(default_factory=list)
    supporting_evidence_notes: list[str] = Field(default_factory=list)
    charts: list[ChartArtifact] = Field(default_factory=list)
    follow_up_questions: list[str] = Field(
        default_factory=list,
        description="3 concrete analytical drill-down questions the user should ask next based on the anomalies, top drivers, or risks uncovered."
    )
    report_file_path: str = ""
    report_markdown: str = ""
    report_html: str = ""
    is_successful: bool = True