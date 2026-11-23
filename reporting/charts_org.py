from pathlib import Path
import re
import pandas as pd
import plotly.express as px

CHARTS_DIR = Path(__file__).resolve().parents[1] / "outputs" / "charts"
CHARTS_DIR.mkdir(parents=True, exist_ok=True)


def _safe_filename(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", name).strip("_")[:60] or "chart"


def build_plotly_chart(
    rows: list[dict],
    title: str,
    task_id: str = "task_1",
    chart_type: str = "auto",
) -> dict:
    """Build an interactive Plotly chart from query rows and save it to outputs/charts/."""
    if not rows:
        return {"success": False, "error": "No data rows available to visualize."}

    df = pd.DataFrame(rows)
    numeric_cols = [
        c for c in df.select_dtypes(include="number").columns
        if not c.lower().endswith("id")
    ]
    non_numeric = [c for c in df.columns if c not in df.select_dtypes(include="number").columns]

    if not numeric_cols or not non_numeric:
        return {"success": False, "error": "Insufficient label and numeric columns for charting."}

    time_keywords = ("date", "month", "year", "quarter", "week", "period", "day")
    time_col = next((c for c in non_numeric if any(k in c.lower() for k in time_keywords)), None)
    x_col = time_col or non_numeric[0]
    y_col = numeric_cols[0]

    selected_type = chart_type
    if selected_type == "auto":
        selected_type = "line" if time_col else "bar"

    if selected_type == "line":
        df = df.sort_values(by=x_col)
        fig = px.line(df, x=x_col, y=y_col, markers=True, title=title)
    elif selected_type == "pie":
        fig = px.pie(df, names=x_col, values=y_col, title=title)
    else:
        selected_type = "bar"
        fig = px.bar(df, x=x_col, y=y_col, text_auto=".2s", title=title)

    fig.update_layout(template="plotly_white", xaxis_title=x_col, yaxis_title=y_col)

    filename = f"{_safe_filename(task_id)}_{_safe_filename(title)}.html"
    out_path = CHARTS_DIR / filename
    fig.write_html(str(out_path), include_plotlyjs="cdn")

    return {
        "success": True,
        "task_id": task_id,
        "chart_type": selected_type,
        "title": title,
        "html_path": str(out_path),
        "figure_json": fig.to_json(),
    }