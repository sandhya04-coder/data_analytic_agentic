from datetime import datetime
from pathlib import Path
import re

REPORTS_DIR = Path(__file__).resolve().parents[1] / "outputs" / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def _safe_filename(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", name).strip("_")[:60] or "report"


def render_and_save_report(report_data: dict) -> dict:
    """Render an ExecutiveReport dictionary into clean Markdown and save to outputs/reports/."""
    lines = [
        f"# {report_data.get('report_title', 'Business Intelligence Report')}",
        f"*Generated on {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
        "",
        f"**Question:** {report_data.get('original_question', '')}",
        "",
        "## Business Summary",
        report_data.get("business_summary", ""),
        "",
        "## Key Findings",
    ]

    for item in report_data.get("key_findings_summary", []):
        lines.append(f"- {item}")

    root_cause = report_data.get("root_cause_section", "").strip()
    if root_cause:
        lines.extend(["", "## Root Cause Analysis", root_cause])

    charts = report_data.get("charts", [])
    if charts:
        lines.extend(["", "## Visualizations"])
        for ch in charts:
            lines.append(f"- **{ch.get('title')}** ({ch.get('chart_type')}): `{ch.get('html_path')}`")

    recommendations = report_data.get("recommendations", [])
    if recommendations:
        lines.extend(["", "## Strategic Recommendations"])
        for idx, rec in enumerate(recommendations, start=1):
            lines.append(
                f"{idx}. **[{rec.get('priority', 'medium').upper()}] {rec.get('title')}**: "
                f"{rec.get('action')} *(Rationale: {rec.get('rationale')} | Expected Impact: {rec.get('expected_impact')})*"
            )

    evidence = report_data.get("supporting_evidence_notes", [])
    if evidence:
        lines.extend(["", "## Supporting Evidence & Caveats"])
        for note in evidence:
            lines.append(f"- {note}")

    markdown_text = "\n".join(lines).strip() + "\n"
    filename = f"{_safe_filename(report_data.get('report_title', 'report'))}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    out_path = REPORTS_DIR / filename
    out_path.write_text(markdown_text, encoding="utf-8")

    return {
        "success": True,
        "report_file_path": str(out_path),
        "report_markdown": markdown_text,
    }