import pandas as pd


def compute_business_metrics(rows: list[dict], metric_columns: list[str] | None = None) -> dict:
    """Compute deterministic summary statistics, totals, shares, and top/bottom records."""
    if not rows:
        return {"row_count": 0, "metrics": {}, "note": "No rows returned to analyze."}

    df = pd.DataFrame(rows)
    numeric_cols = metric_columns or df.select_dtypes(include="number").columns.tolist()
    numeric_cols = [c for c in numeric_cols if c in df.columns]

    # Exclude ID columns from KPI aggregations
    kpi_cols = [c for c in numeric_cols if not c.lower().endswith("id")]

    summary: dict = {"row_count": int(len(df)), "metrics": {}}
    label_cols = [c for c in df.columns if c not in numeric_cols]
    label_col = label_cols[0] if label_cols else None

    for col in kpi_cols:
        series = pd.to_numeric(df[col], errors="coerce").dropna()
        if series.empty:
            continue

        total = float(series.sum())
        col_stats: dict = {
            "total": round(total, 2),
            "mean": round(float(series.mean()), 2),
            "median": round(float(series.median()), 2),
            "min": round(float(series.min()), 2),
            "max": round(float(series.max()), 2),
            "std": round(float(series.std(ddof=0)), 2),
        }

        if label_col and len(df) > 1:
            ranked = df[[label_col, col]].dropna().sort_values(by=col, ascending=False)
            top_row = ranked.iloc[0]
            bottom_row = ranked.iloc[-1]
            col_stats["top_contributor"] = {
                "label": str(top_row[label_col]),
                "value": round(float(top_row[col]), 2),
                "share_pct": round((float(top_row[col]) / total) * 100, 2) if total else 0.0,
            }
            col_stats["bottom_contributor"] = {
                "label": str(bottom_row[label_col]),
                "value": round(float(bottom_row[col]), 2),
            }

        summary["metrics"][col] = col_stats

    return summary