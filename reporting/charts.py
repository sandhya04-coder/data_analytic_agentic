from pathlib import Path
import re
import textwrap
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

CHARTS_DIR = Path(__file__).resolve().parents[1] / "outputs" / "charts"
CHARTS_DIR.mkdir(parents=True, exist_ok=True)

PALETTE = ["#1e3a8a", "#0284c7", "#0d9488", "#d97706", "#7c3aed", "#db2777", "#4f46e5", "#059669"]


def _safe_filename(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", name).strip("_")[:60] or "chart"


def _humanize_label(col: str) -> str:
    return col.replace("_", " ").strip().title()


def _wrap_title(text: str, width: int = 58) -> str:
    return "<br>".join(textwrap.wrap(text, width=width))


def _pick_y_columns(numeric_cols: list[str]) -> tuple[str, str | None]:
    """Return (primary_metric_col, optional_level_metric_col)."""
    delta_keywords = ["absolute_change", "change", "diff", "variance", "growth"]
    level_keywords = ["q1", "2018", "total_revenue", "revenue", "sales", "profit", "amount", "total", "count"]

    delta_col = next(
        (c for c in numeric_cols if any(k in c.lower() for k in delta_keywords) and "pct" not in c.lower() and "percentage" not in c.lower()),
        None,
    )
    level_col = next(
        (c for c in numeric_cols if any(k in c.lower() for k in level_keywords) and "pct" not in c.lower() and "percentage" not in c.lower()),
        numeric_cols[0],
    )
    return (delta_col or level_col), level_col


def _style_figure(fig: go.Figure, title: str, subtitle: str = "", height: int = 490) -> go.Figure:
    wrapped_title = _wrap_title(title, width=58)
    full_title = (
        f"<b>{wrapped_title}</b><br><span style='font-size:12px;color:#475569;'>{subtitle}</span>"
        if subtitle
        else f"<b>{wrapped_title}</b>"
    )
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        height=height,
        margin=dict(l=65, r=165, t=105, b=80),
        title=dict(
            text=full_title,
            x=0.01,
            y=0.96,
            xanchor="left",
            yanchor="top",
            font=dict(size=15, color="#0f172a"),
        ),
        legend=dict(
            orientation="v",
            yanchor="top",
            y=1.0,
            xanchor="left",
            x=1.02,
            bgcolor="#f8fafc",
            bordercolor="#cbd5e1",
            borderwidth=1,
            font=dict(size=11, color="#0f172a"),
            title=dict(font=dict(size=12, color="#0f172a")),
        ),
        font=dict(family="Inter, Segoe UI, sans-serif", color="#0f172a"),
        uniformtext_minsize=10,
        uniformtext_mode="hide",
    )
    fig.update_xaxes(
        automargin=True,
        tickangle=-20,
        title_standoff=14,
        tickfont=dict(color="#1e293b"),
        title_font=dict(color="#0f172a"),
        gridcolor="#e2e8f0",
    )
    fig.update_yaxes(
        automargin=True,
        title_standoff=10,
        tickfont=dict(color="#1e293b"),
        title_font=dict(color="#0f172a"),
        gridcolor="#e2e8f0",
    )
    return fig


def build_visual_suite(
    rows: list[dict],
    title: str,
    task_id: str = "task_1",
) -> list[dict]:
    """
    Generate a suite of complementary Plotly visualizations from query rows:
    1. Primary Ranking / Period Comparison / Trend Chart
    2. 2D Cross-Segment Heatmap (when 2 categorical dimensions exist)
    3. Hierarchical Portfolio Treemap (for positive share composition)
    3B. Side-by-Side Period Comparison (when 2 period columns exist)
    4. Pareto 80/20 Cumulative Contribution Chart
    """
    if not rows or len(rows) < 2:
        return []

    df = pd.DataFrame(rows)
    numeric_cols = [
        c for c in df.select_dtypes(include="number").columns
        if not c.lower().endswith("id")
    ]
    non_numeric = [c for c in df.columns if c not in df.select_dtypes(include="number").columns]

    if not numeric_cols or not non_numeric:
        return []

    time_keywords = ("date", "month", "year", "quarter", "week", "period", "day")
    time_col = next((c for c in non_numeric if any(k in c.lower() for k in time_keywords)), None)

    dim1 = time_col or non_numeric[0]
    dim2 = non_numeric[1] if (not time_col and len(non_numeric) >= 2) else None
    primary_y, level_y = _pick_y_columns(numeric_cols)
    clean_title = title.split("(")[0].strip()
    has_negatives = (df[primary_y] < 0).any() and (df[primary_y] > 0).any()

    artifacts: list[dict] = []

    def _register(fig: go.Figure, chart_type: str, chart_title: str, suffix: str):
        filename = f"{_safe_filename(task_id)}_{suffix}.html"
        out_path = CHARTS_DIR / filename
        fig.write_html(str(out_path), include_plotlyjs="cdn")
        artifacts.append({
            "success": True,
            "task_id": task_id,
            "chart_type": chart_type,
            "title": chart_title,
            "html_path": str(out_path),
            "figure_json": fig.to_json(),
        })

    # -----------------------------------------------------------------------
    # VIEW 1: Primary Trend Line OR Grouped/Diverging Variance Bar
    # -----------------------------------------------------------------------
    if time_col:
        df_sorted = df.sort_values(by=time_col)
        fig1 = px.line(
            df_sorted,
            x=time_col,
            y=primary_y,
            color=dim2,
            markers=True,
            color_discrete_sequence=PALETTE,
            labels={time_col: _humanize_label(time_col), primary_y: _humanize_label(primary_y)},
        )
        fig1.update_traces(line=dict(width=3), marker=dict(size=8))
        _style_figure(fig1, f"{clean_title} — Trajectory", f"Time-series progression of {_humanize_label(primary_y)}")
        _register(fig1, "line", f"{clean_title} (Trend)", "1_trend")
    else:
        axis_labels = {
            dim1: _humanize_label(dim1),
            primary_y: _humanize_label(primary_y),
        }
        if dim2:
            axis_labels[dim2] = _humanize_label(dim2)

        if dim2 and df[dim2].nunique() <= 12:
            top_d1 = df.groupby(dim1)[primary_y].apply(lambda s: s.abs().sum()).nlargest(8).index
            plot_df = df[df[dim1].isin(top_d1)]
            fig1 = px.bar(
                plot_df,
                x=dim1,
                y=primary_y,
                color=dim2,
                barmode="relative" if has_negatives else "group",
                color_discrete_sequence=PALETTE,
                labels=axis_labels,
            )
        elif has_negatives:
            plot_df = df.head(15).iloc[::-1]
            fig1 = px.bar(
                plot_df,
                x=primary_y,
                y=dim1,
                orientation="h",
                color=primary_y,
                color_continuous_scale=["#dc2626", "#f1f5f9", "#059669"],
                color_continuous_midpoint=0,
                text_auto=".3s",
                labels=axis_labels,
            )
            fig1.update_traces(textposition="outside", cliponaxis=False)
        else:
            plot_df = df.head(12).iloc[::-1]
            fig1 = px.bar(
                plot_df,
                x=primary_y,
                y=dim1,
                orientation="h",
                text_auto=".3s",
                color_discrete_sequence=["#1e3a8a"],
                labels=axis_labels,
            )
            fig1.update_traces(textposition="outside", cliponaxis=False)

        if has_negatives:
            if dim2:
                fig1.add_hline(y=0, line_width=1.5, line_color="#64748b")
            else:
                fig1.add_vline(x=0, line_width=1.5, line_color="#64748b")

        _style_figure(
            fig1,
            f"{clean_title} — Primary Comparison",
            f"Breakdown by {_humanize_label(dim1)}" + (f" & {_humanize_label(dim2)}" if dim2 else ""),
        )
        if not dim2:
            fig1.update_layout(margin=dict(l=65, r=80, t=105, b=80))
        _register(fig1, "bar", f"{clean_title} (Comparison)", "1_comparison")

    # -----------------------------------------------------------------------
    # VIEW 2: 2D Cross-Segment Heatmap Matrix (when 2 categorical columns exist)
    # -----------------------------------------------------------------------
    if dim2 and df[dim1].nunique() >= 2 and df[dim2].nunique() >= 2:
        pivot = df.pivot_table(index=dim1, columns=dim2, values=primary_y, aggfunc="sum", fill_value=0)
        fig2 = px.imshow(
            pivot,
            text_auto=".2s",
            aspect="auto",
            color_continuous_scale=["#dc2626", "#f8fafc", "#059669"] if has_negatives else "Blues",
            color_continuous_midpoint=0 if has_negatives else None,
        )
        fig2.update_xaxes(title_text=_humanize_label(dim2), side="bottom")
        fig2.update_yaxes(title_text=_humanize_label(dim1))
        _style_figure(
            fig2,
            f"Cross-Segment Matrix: {_humanize_label(dim1)} × {_humanize_label(dim2)}",
            f"Cell values represent {_humanize_label(primary_y)}",
            height=470,
        )
        fig2.update_layout(margin=dict(l=65, r=85, t=105, b=80))
        _register(fig2, "heatmap", f"{_humanize_label(dim1)} × {_humanize_label(dim2)} Heatmap", "2_heatmap")

    # -----------------------------------------------------------------------
    # VIEW 3: Hierarchical Portfolio Treemap (using positive level metric)
    # -----------------------------------------------------------------------
    if level_y:
        tree_df = df[df[level_y] > 0].copy()
        if len(tree_df) >= 2:
            path_cols = [dim1, dim2] if dim2 else [dim1]
            for c in path_cols:
                tree_df[c] = tree_df[c].fillna("Unspecified").astype(str)
            fig3 = px.treemap(
                tree_df,
                path=path_cols,
                values=level_y,
                color=primary_y if has_negatives else level_y,
                color_continuous_scale=["#dc2626", "#e2e8f0", "#059669"] if has_negatives else "Tealgrn",
                color_continuous_midpoint=0 if has_negatives else None,
            )
            fig3.update_traces(textinfo="label+value+percent parent")
            _style_figure(
                fig3,
                f"Portfolio Share Composition ({_humanize_label(level_y)})",
                "Proportional box size reflects volume; color reflects performance",
                height=460,
            )
            fig3.update_layout(margin=dict(l=25, r=85, t=105, b=30))
            _register(fig3, "treemap", "Portfolio Composition Treemap", "3_treemap")

    # -----------------------------------------------------------------------
    # VIEW 3B: Side-by-Side Period Comparison (when 2 period columns exist)
    # -----------------------------------------------------------------------
    period_cols = [
        c for c in numeric_cols
        if any(tag in c.lower() for tag in ("2016", "2017", "2018", "q1", "q2", "q3", "q4", "prev", "curr", "baseline", "target"))
        and "change" not in c.lower()
        and "pct" not in c.lower()
    ]
    if len(period_cols) >= 2:
        comp_df = df.groupby(dim1, as_index=False)[period_cols[:2]].sum()
        comp_melted = comp_df.melt(id_vars=[dim1], value_vars=period_cols[:2], var_name="Period", value_name="Value")
        comp_melted["Period"] = comp_melted["Period"].apply(_humanize_label)
        fig_period = px.bar(
            comp_melted,
            x=dim1,
            y="Value",
            color="Period",
            barmode="group",
            text_auto=".3s" if len(comp_df) <= 6 else False,
            color_discrete_sequence=["#94a3b8", "#1e3a8a"],
            labels={dim1: _humanize_label(dim1), "Value": "Revenue (USD)"},
        )
        if len(comp_df) <= 6:
            fig_period.update_traces(textposition="outside", cliponaxis=False)
        _style_figure(
            fig_period,
            f"Period-over-Period Comparison by {_humanize_label(dim1)}",
            f"Direct comparison of {_humanize_label(period_cols[0])} vs. {_humanize_label(period_cols[1])}",
            height=460,
        )
        fig_period.update_layout(margin=dict(l=65, r=140, t=105, b=80))
        _register(fig_period, "period_bar", "Period-over-Period Side-by-Side Comparison", "3b_period_comparison")

    # -----------------------------------------------------------------------
    # VIEW 4: Pareto 80/20 Concentration Curve
    # -----------------------------------------------------------------------
    if level_y:
        pareto_df = (
            df.groupby(dim1, as_index=False)[level_y]
            .sum()
            .query(f"`{level_y}` > 0")
            .sort_values(by=level_y, ascending=False)
            .head(15)
        )
        if len(pareto_df) >= 3:
            pareto_df["cum_pct"] = (pareto_df[level_y].cumsum() / pareto_df[level_y].sum()) * 100
            fig4 = make_subplots(specs=[[{"secondary_y": True}]])
            fig4.add_trace(
                go.Bar(
                    x=pareto_df[dim1],
                    y=pareto_df[level_y],
                    name=_humanize_label(level_y),
                    marker_color="#0284c7",
                ),
                secondary_y=False,
            )
            fig4.add_trace(
                go.Scatter(
                    x=pareto_df[dim1],
                    y=pareto_df["cum_pct"],
                    name="Cumulative %",
                    mode="lines+markers",
                    line=dict(color="#d97706", width=3),
                    marker=dict(size=7),
                ),
                secondary_y=True,
            )
            fig4.add_hline(y=80, line_dash="dash", line_color="#dc2626", secondary_y=True)
            fig4.update_xaxes(title_text=_humanize_label(dim1))
            fig4.update_yaxes(title_text=_humanize_label(level_y), secondary_y=False)
            fig4.update_yaxes(title_text="Cumulative Share (%)", range=[0, 105], secondary_y=True)
            _style_figure(
                fig4,
                f"Pareto 80/20 Concentration by {_humanize_label(dim1)}",
                "Bars show segment volume; amber line tracks cumulative contribution against the 80% threshold",
                height=460,
            )
            fig4.update_layout(margin=dict(l=65, r=140, t=105, b=80))
            _register(fig4, "pareto", f"Pareto 80/20 Concentration ({_humanize_label(dim1)})", "4_pareto")

    return artifacts


def build_plotly_chart(
    rows: list[dict],
    title: str,
    task_id: str = "task_1",
    chart_type: str = "auto",
) -> dict:
    """Backward-compatible single-chart wrapper returning the primary chart from build_visual_suite."""
    suite = build_visual_suite(rows=rows, title=title, task_id=task_id)
    if not suite:
        return {"success": False, "error": "Insufficient data for charting."}
    if chart_type != "auto":
        match = next((c for c in suite if c["chart_type"] == chart_type), None)
        if match:
            return match
    return suite[0]