from datetime import datetime
import html
from pathlib import Path
import re
import plotly.io as pio

REPORTS_DIR = Path(__file__).resolve().parents[1] / "outputs" / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def _safe_filename(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", name).strip("_")[:60] or "report"


def _build_html_report(report_data: dict) -> str:
    """Build a self-contained executive HTML brief with live interactive Plotly visualizations."""
    title = html.escape(report_data.get("report_title", "Executive Business Intelligence Brief"))
    subtitle = html.escape(report_data.get("subtitle", ""))
    question = html.escape(report_data.get("original_question", ""))
    summary = html.escape(report_data.get("business_summary", ""))
    generated_at = datetime.now().strftime("%B %d, %Y at %H:%M")

    # KPI Cards
    kpi_html = ""
    for k in report_data.get("headline_kpis", []):
        sentiment = k.get("sentiment", "neutral")
        delta_cls = "pos" if sentiment == "positive" else ("neg" if sentiment == "negative" else "neu")
        delta_txt = html.escape(k.get("delta", ""))
        kpi_html += f"""
        <div class="kpi-card">
            <div class="kpi-label">{html.escape(k.get('label', ''))}</div>
            <div class="kpi-value">{html.escape(k.get('value', ''))}</div>
            {f'<div class="kpi-delta {delta_cls}">{delta_txt}</div>' if delta_txt else ''}
        </div>"""

    # Live Embedded Plotly Charts
    charts_html = ""
    for idx, ch in enumerate(report_data.get("charts", [])):
        fig_json = ch.get("figure_json", "")
        if not fig_json:
            continue
        fig = pio.from_json(fig_json)
        div_html = pio.to_html(
            fig,
            full_html=False,
            include_plotlyjs="cdn" if idx == 0 else False,
            config={"responsive": True},
        )
        charts_html += f'<div class="chart-box">{div_html}</div>'

    # Segment Drivers Table
    drivers_rows = ""
    for d in report_data.get("top_drivers", []):
        drivers_rows += f"""
        <tr>
            <td><strong>{html.escape(d.get('segment', ''))}</strong></td>
            <td><span class="pill">{html.escape(d.get('role', ''))}</span></td>
            <td><strong>{html.escape(d.get('metric_value', ''))}</strong></td>
            <td>{html.escape(d.get('takeaway', ''))}</td>
        </tr>"""

    # Findings & Root Cause
    findings_li = "".join(
        f"<li>{html.escape(item)}</li>" for item in report_data.get("key_findings_summary", [])
    )
    root_cause = html.escape(report_data.get("root_cause_section", "").strip())

    # Recommendations
    recs_html = ""
    for rec in report_data.get("recommendations", []):
        prio = rec.get("priority", "medium").lower()
        recs_html += f"""
        <div class="rec {prio}">
            <span class="prio-tag">{prio.upper()} PRIORITY</span>
            <strong>{html.escape(rec.get('title', ''))}</strong>
            <p>{html.escape(rec.get('action', ''))}</p>
            <small><strong>Evidence:</strong> {html.escape(rec.get('rationale', ''))} &nbsp;|&nbsp;
            <strong>Expected Impact:</strong> {html.escape(rec.get('expected_impact', ''))}</small>
        </div>"""

    evidence_li = "".join(
        f"<li>{html.escape(n)}</li>"
        for n in dict.fromkeys(report_data.get("supporting_evidence_notes", []))
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>{title}</title>
<style>
  body {{ font-family: 'Segoe UI', Inter, system-ui, sans-serif; background: #f1f5f9; color: #0f172a; margin: 0; padding: 32px; }}
  .container {{ max-width: 1120px; margin: 0 auto; background: #ffffff; border-radius: 16px; box-shadow: 0 10px 30px rgba(15,23,42,0.08); overflow: hidden; }}
  .header {{ background: linear-gradient(135deg, #0f172a, #1e3a8a); color: #fff; padding: 32px 40px; }}
  .header h1 {{ margin: 0 0 6px 0; font-size: 26px; }}
  .header p {{ margin: 0; color: #cbd5e1; font-size: 14px; }}
  .content {{ padding: 32px 40px; }}
  .kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 16px; margin-bottom: 28px; }}
  .kpi-card {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 16px 20px; }}
  .kpi-label {{ font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em; color: #64748b; font-weight: 600; }}
  .kpi-value {{ font-size: 24px; font-weight: 700; color: #0f172a; margin-top: 4px; }}
  .kpi-delta {{ font-size: 13px; font-weight: 600; margin-top: 4px; }}
  .pos {{ color: #059669; }} .neg {{ color: #dc2626; }} .neu {{ color: #475569; }}
  .exec-box {{ background: #eff6ff; border-left: 4px solid #1d4ed8; padding: 18px 22px; border-radius: 8px; line-height: 1.6; margin-bottom: 28px; }}
  h2 {{ font-size: 18px; color: #0f172a; border-bottom: 2px solid #e2e8f0; padding-bottom: 8px; margin-top: 32px; }}
  .chart-grid {{ display: grid; grid-template-columns: 1fr; gap: 22px; margin-top: 16px; }}
  .chart-box {{ border: 1px solid #e2e8f0; border-radius: 12px; padding: 12px; background: #fff; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 14px; }}
  th {{ background: #f8fafc; text-align: left; padding: 10px 12px; border-bottom: 2px solid #cbd5e1; color: #334155; }}
  td {{ padding: 10px 12px; border-bottom: 1px solid #e2e8f0; }}
  .pill {{ background: #e0f2fe; color: #0369a1; padding: 2px 8px; border-radius: 999px; font-size: 12px; font-weight: 600; }}
  .rec {{ border-left: 4px solid #0284c7; background: #f8fafc; padding: 14px 18px; border-radius: 8px; margin-bottom: 12px; }}
  .rec.high {{ border-left-color: #dc2626; }} .rec.medium {{ border-left-color: #d97706; }} .rec.low {{ border-left-color: #16a34a; }}
  .prio-tag {{ font-size: 11px; font-weight: 700; background: #e2e8f0; padding: 2px 7px; border-radius: 4px; margin-right: 8px; }}
  ul {{ line-height: 1.7; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>{title}</h1>
    <p>{subtitle}</p>
    <p style="margin-top:8px;font-size:12px;">Generated {generated_at} • Query: "{question}"</p>
  </div>
  <div class="content">
    {f'<div class="kpi-grid">{kpi_html}</div>' if kpi_html else ''}
    <h2>Executive Summary</h2>
    <div class="exec-box">{summary}</div>
    {f'<h2>Interactive Visual Analytics ({len(report_data.get("charts", []))} Views)</h2><div class="chart-grid">{charts_html}</div>' if charts_html else ''}
    {f'<h2>Segment Drivers & Risk Breakdown</h2><table><thead><tr><th>Segment</th><th>Classification</th><th>Performance</th><th>Takeaway</th></tr></thead><tbody>{drivers_rows}</tbody></table>' if drivers_rows else ''}
    <h2>Key Findings</h2>
    <ul>{findings_li}</ul>
    {f'<h2>Root Cause & Driver Decomposition</h2><p style="line-height:1.6;">{root_cause}</p>' if root_cause else ''}
    <h2>Strategic Recommendations</h2>
    {recs_html}
    <h2>Methodology & Data Governance</h2>
    <ul>{evidence_li}</ul>
  </div>
</div>
</body>
</html>"""


def render_and_save_report(report_data: dict) -> dict:
    """Render and save both Markdown (.md) and interactive HTML (.html with live charts) reports."""
    lines = [
        f"# {report_data.get('report_title', 'Executive Business Intelligence Brief')}",
    ]
    if report_data.get("subtitle"):
        lines.append(f"**{report_data['subtitle']}**")
    lines.extend([
        f"*Generated: {datetime.now().strftime('%B %d, %Y at %H:%M')} • Query: \"{report_data.get('original_question', '')}\"*",
        "",
        "---",
        "",
        "## Executive Summary",
        report_data.get("business_summary", ""),
        "",
    ])

    kpis = report_data.get("headline_kpis", [])
    if kpis:
        lines.extend(["## Key Performance Indicators", "| Metric | Value | Variance / Context |", "| :--- | :--- | :--- |"])
        for k in kpis:
            lines.append(f"| **{k.get('label')}** | {k.get('value')} | {k.get('delta') or '—'} |")
        lines.append("")

    drivers = report_data.get("top_drivers", [])
    if drivers:
        lines.extend(["## Segment Drivers & Risk Breakdown", "| Segment | Classification | Performance | Takeaway |", "| :--- | :--- | :--- | :--- |"])
        for d in drivers:
            lines.append(f"| **{d.get('segment')}** | {d.get('role')} | {d.get('metric_value')} | {d.get('takeaway')} |")
        lines.append("")

    findings = report_data.get("key_findings_summary", [])
    if findings:
        lines.append("## Key Findings")
        for item in findings:
            lines.append(f"- {item}")
        lines.append("")

    root_cause = report_data.get("root_cause_section", "").strip()
    if root_cause:
        lines.extend(["## Root Cause & Driver Decomposition", root_cause, ""])

    recommendations = report_data.get("recommendations", [])
    if recommendations:
        lines.append("## Strategic Recommendations")
        for idx, rec in enumerate(recommendations, start=1):
            lines.extend([
                f"### {idx}. [{rec.get('priority', 'medium').upper()}] {rec.get('title')}",
                f"- **Action:** {rec.get('action')}",
                f"- **Quantified Rationale:** {rec.get('rationale')}",
                f"- **Expected Impact:** {rec.get('expected_impact')}",
                "",
            ])

    evidence = list(dict.fromkeys(report_data.get("supporting_evidence_notes", [])))
    if evidence:
        lines.append("## Methodology & Data Governance")
        for note in evidence:
            lines.append(f"- {note}")

    markdown_text = "\n".join(lines).strip() + "\n"
    html_text = _build_html_report(report_data)

    stem = f"{_safe_filename(report_data.get('report_title', 'report'))}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    md_path = REPORTS_DIR / f"{stem}.md"
    html_path = REPORTS_DIR / f"{stem}.html"
    md_path.write_text(markdown_text, encoding="utf-8")
    html_path.write_text(html_text, encoding="utf-8")

    return {
        "success": True,
        "report_file_path": str(html_path),
        "report_markdown": markdown_text,
        "report_html": html_text,
    }