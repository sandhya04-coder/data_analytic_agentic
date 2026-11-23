from langchain_core.tools import tool
from reporting.charts import build_plotly_chart
from reporting.executive_report import render_and_save_report


@tool
def create_visualization(
    rows: list[dict],
    title: str,
    task_id: str = "task_1",
    chart_type: str = "auto",
) -> dict:
    """Generate an interactive Plotly chart from query rows and save it as HTML."""
    return build_plotly_chart(
        rows=rows,
        title=title,
        task_id=task_id,
        chart_type=chart_type,
    )


@tool
def export_business_report(report_data: dict) -> dict:
    """Render and save a structured executive business intelligence report as Markdown."""
    return render_and_save_report(report_data=report_data)