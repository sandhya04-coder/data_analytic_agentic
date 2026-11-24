from pathlib import Path
import re
import textwrap
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from schemas.reporting_schema import ChartSpec

CHARTS_DIR = Path(__file__).resolve().parents[1] / "outputs" / "charts"
CHARTS_DIR.mkdir(parents=True, exist_ok=True)

PALETTE = ["#1e3a8a", "#0284c7", "#0d9488", "#d97706", "#7c3aed", "#db2777", "#4f46e5", "#059669"]
NON_ADDITIVE = ("avg", "average", "mean", "rate", "ratio", "pct", "percentage", "score", "aov")


def _safe_filename(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", name).strip("_")[:60] or "chart"


def _humanize(col: str) -> str:
    return col.replace("_", " ").strip().title()


def _style_figure(fig: go.Figure, title: str, subtitle: str = "", height: int = 470) -> go.Figure:
    wrapped = "<br>".join(textwrap.wrap(title, width=60))
    full_title = (
        f"<b>{wrapped}</b><br><span style='font-size:12px;color:#475569;'>{subtitle}</span>"
        if subtitle
        else f"<b>{wrapped}</b>"
    )
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        height=height,
        margin=dict(l=65, r=150, t=100, b=75),
        title=dict(text=full_title, x=0.01, y=0.96, xanchor="left", yanchor="top", font=dict(size=15, color="#0f172a")),
        legend=dict(
            orientation="v", yanchor="top", y=1.0, xanchor="left", x=1.02,
            bgcolor="#f8fafc", bordercolor="#cbd5e1", borderwidth=1, font=dict(size=11, color="#0f172a"),
        ),
        font=dict(family="Inter, Segoe UI, sans-serif", color="#0f172a"),
    )
    fig.update_xaxes(automargin=True, tickangle=-20, gridcolor="#e2e8f0", tickfont=dict(color="#1e293b"))
    fig.update_yaxes(automargin=True, gridcolor="#e2e8f0", tickfont=dict(color="#1e293b"))
    return fig


def render_chart_specs(
    rows_by_task: dict[str, list[dict]],
    specs: list[ChartSpec],
) -> list[dict]:
    """Deterministically validate and render LLM-selected ChartSpecs into Plotly figures."""
    artifacts: list[dict] = []

    for idx, spec in enumerate(specs, 1):
        rows = rows_by_task.get(spec.task_id) or next(iter(rows_by_task.values()), [])
        if not rows or len(rows) < 2:
            continue

        df = pd.DataFrame(rows)
        if spec.x_col not in df.columns or spec.y_col not in df.columns:
            continue

        color_col = spec.color_col if (spec.color_col and spec.color_col in df.columns) else None
        ctype = spec.chart_type
        labels = {spec.x_col: _humanize(spec.x_col), spec.y_col: _humanize(spec.y_col)}
        if color_col:
            labels[color_col] = _humanize(color_col)

        # Guardrails against semantically invalid chart types
        if ctype == "treemap" and (len(df) < 3 or any(k in spec.y_col.lower() for k in NON_ADDITIVE)):
            ctype = "bar"
        if ctype == "line" and df[spec.x_col].nunique() < 4:
            ctype = "grouped_bar" if color_col else "bar"

        fig: go.Figure | None = None

        if ctype == "line":
            df_sorted = df.sort_values(by=spec.x_col)
            fig = px.line(df_sorted, x=spec.x_col, y=spec.y_col, color=color_col, markers=True,
                          color_discrete_sequence=PALETTE, labels=labels)
            fig.update_traces(line=dict(width=3), marker=dict(size=7))

        elif ctype == "grouped_bar" and color_col:
            plot_df = df.copy()
            plot_df[color_col] = plot_df[color_col].astype(str)
            # Keep top 12 x-categories by total y_col, preserving ALL color series (e.g. both 2017 & 2018)
            top_x = (
                plot_df.groupby(spec.x_col, observed=False)[spec.y_col]
                .sum()
                .nlargest(12)
                .index
            )
            plot_df = plot_df[plot_df[spec.x_col].isin(top_x)]
            fig = px.bar(
                plot_df,
                x=spec.x_col,
                y=spec.y_col,
                color=color_col,
                barmode="group",
                text_auto=".3s" if len(plot_df) <= 12 else False,
                color_discrete_sequence=PALETTE,
                labels=labels,
            )
            if len(plot_df) <= 12:
                fig.update_traces(textposition="outside", cliponaxis=False)

        elif ctype == "scatter":
            fig = px.scatter(df.head(100), x=spec.x_col, y=spec.y_col, color=color_col,
                             color_discrete_sequence=PALETTE, labels=labels)
            fig.update_traces(marker=dict(size=10, opacity=0.85))

        elif ctype == "heatmap" and color_col and df[spec.x_col].nunique() >= 2 and df[color_col].nunique() >= 2:
            pivot = df.pivot_table(index=spec.x_col, columns=color_col, values=spec.y_col, aggfunc="sum", fill_value=0)
            fig = px.imshow(pivot, text_auto=".2s", aspect="auto", color_continuous_scale="Blues")
            fig.update_xaxes(title_text=_humanize(color_col))
            fig.update_yaxes(title_text=_humanize(spec.x_col))

        elif ctype == "treemap":
            tree_df = df[df[spec.y_col] > 0].copy()
            if len(tree_df) >= 3:
                path = [spec.x_col, color_col] if color_col else [spec.x_col]
                for c in path:
                    tree_df[c] = tree_df[c].fillna("Unspecified").astype(str)
                fig = px.treemap(tree_df, path=path, values=spec.y_col, color=spec.y_col, color_continuous_scale="Tealgrn")
                fig.update_traces(textinfo="label+value+percent parent")

        elif ctype == "pareto" and len(df) >= 4:
            p_df = df.groupby(spec.x_col, as_index=False)[spec.y_col].sum().sort_values(by=spec.y_col, ascending=False).head(15)
            p_df["cum_pct"] = (p_df[spec.y_col].cumsum() / p_df[spec.y_col].sum()) * 100
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            fig.add_trace(go.Bar(x=p_df[spec.x_col], y=p_df[spec.y_col], name=_humanize(spec.y_col), marker_color="#0284c7"), secondary_y=False)
            fig.add_trace(go.Scatter(x=p_df[spec.x_col], y=p_df["cum_pct"], name="Cumulative %", mode="lines+markers", line=dict(color="#d97706", width=3)), secondary_y=True)
            fig.add_hline(y=80, line_dash="dash", line_color="#dc2626", secondary_y=True)
            fig.update_yaxes(title_text=_humanize(spec.y_col), secondary_y=False)
            fig.update_yaxes(title_text="Cumulative Share (%)", range=[0, 105], secondary_y=True)

        if fig is None:
            # If x_col is constant (e.g., ABAC-filtered to 1 state) and color_col varies (e.g., year), plot color_col
            bar_cat = color_col if (color_col and df[spec.x_col].nunique() == 1 and df[color_col].nunique() > 1) else spec.x_col
            plot_df = df.head(12).iloc[::-1]
            plot_df[bar_cat] = plot_df[bar_cat].astype(str)
            fig = px.bar(
                plot_df,
                x=spec.y_col,
                y=bar_cat,
                orientation="h",
                text_auto=".3s",
                color_discrete_sequence=["#1e3a8a"],
                labels={spec.y_col: _humanize(spec.y_col), bar_cat: _humanize(bar_cat)},
            )
            fig.update_traces(textposition="outside", cliponaxis=False)
            ctype = "bar"

        _style_figure(fig, spec.title, spec.subtitle)
        out_path = CHARTS_DIR / f"{_safe_filename(spec.task_id)}_{idx}_{ctype}.html"
        fig.write_html(str(out_path), include_plotlyjs="cdn")
        artifacts.append({
            "success": True,
            "task_id": spec.task_id,
            "chart_type": ctype,
            "title": spec.title,
            "html_path": str(out_path),
            "figure_json": fig.to_json(),
        })

    return artifacts

def build_plotly_chart(
    rows: list[dict],
    title: str,
    task_id: str = "task_1",
    chart_type: str = "auto",
) -> dict:
    """Backward-compatible single-chart wrapper for tools/reporting_tools.py."""
    if not rows or len(rows) < 2:
        return {"success": False, "error": "Insufficient data for charting."}
    df = pd.DataFrame(rows)
    num_cols = [c for c in df.select_dtypes(include="number").columns if not c.lower().endswith("id")]
    cat_cols = [c for c in df.columns if c not in df.select_dtypes(include="number").columns]
    if not num_cols or not cat_cols:
        return {"success": False, "error": "Need at least one categorical and one numeric column."}
    spec = ChartSpec(
        task_id=task_id,
        chart_type="bar" if chart_type == "auto" else chart_type,
        x_col=cat_cols[0],
        y_col=num_cols[0],
        color_col=cat_cols[1] if len(cat_cols) >= 2 else None,
        title=title,
    )
    rendered = render_chart_specs(rows_by_task={task_id: rows}, specs=[spec])
    return rendered[0] if rendered else {"success": False, "error": "Chart rendering failed."}

