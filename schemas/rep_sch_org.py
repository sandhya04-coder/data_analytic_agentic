from enum import Enum
from pydantic import BaseModel, Field


class RecommendationPriority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Recommendation(BaseModel):
    recommendation_id: str = Field(
        description="Unique identifier, e.g. 'rec_1'."
    )
    title: str = Field(
        description="Short action-oriented recommendation title."
    )
    action: str = Field(
        description="Concrete business action to take."
    )
    rationale: str = Field(
        description="Evidence from the analysis supporting this recommendation."
    )
    priority: RecommendationPriority = Field(
        default=RecommendationPriority.MEDIUM,
        description="Execution priority: 'high', 'medium', or 'low'."
    )
    expected_impact: str = Field(
        description="Expected business outcome or KPI impact."
    )


class ChartArtifact(BaseModel):
    task_id: str = Field(
        description="Task ID whose data is visualized."
    )
    chart_type: str = Field(
        description="Chart type generated: 'bar', 'line', 'pie', or 'table'."
    )
    title: str = Field(
        description="Chart title."
    )
    html_path: str = Field(
        description="Path to saved interactive Plotly HTML file."
    )
    figure_json: str = Field(
        default="",
        description="Serialized Plotly figure JSON for direct rendering in Streamlit."
    )


class ReportNarrative(BaseModel):
    """Strictly typed schema returned by Gemini for executive report synthesis."""
    report_title: str = Field(
        description="Clear, executive-ready report title."
    )
    business_summary: str = Field(
        description="High-level executive overview answering the user's question directly."
    )
    key_findings_summary: list[str] = Field(
        default_factory=list,
        description="Bulleted executive takeaways with exact figures."
    )
    root_cause_section: str = Field(
        default="",
        description="Explanation of contributing drivers if root-cause/comparison analysis was performed, else empty string."
    )
    recommendations: list[Recommendation] = Field(
        default_factory=list,
        description="2-4 actionable, evidence-backed business recommendations."
    )
    supporting_evidence_notes: list[str] = Field(
        default_factory=list,
        description="Audit trail notes referencing SQL queries, date coverage, and caveats."
    )


class ExecutiveReport(BaseModel):
    """Complete Agent 5 deliverable combining narrative, Plotly charts, and exported Markdown report."""
    original_question: str = Field(
        description="Original business question asked by the user."
    )
    report_title: str
    business_summary: str
    key_findings_summary: list[str] = Field(default_factory=list)
    root_cause_section: str = ""
    recommendations: list[Recommendation] = Field(default_factory=list)
    supporting_evidence_notes: list[str] = Field(default_factory=list)
    charts: list[ChartArtifact] = Field(default_factory=list)
    report_file_path: str = Field(
        default="",
        description="Path to the exported Markdown executive report."
    )
    report_markdown: str = Field(
        default="",
        description="Full rendered Markdown report text."
    )
    is_successful: bool = True