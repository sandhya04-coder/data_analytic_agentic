import pandas as pd


def decompose_change(
    baseline_rows: list[dict],
    target_rows: list[dict],
    dimension_column: str,
    metric_column: str,
) -> dict:
    """Decompose total KPI delta between baseline and target periods by dimension."""
    if not baseline_rows or not target_rows:
        return {"error": "Both baseline_rows and target_rows are required for decomposition."}

    base_df = pd.DataFrame(baseline_rows)
    targ_df = pd.DataFrame(target_rows)

    for col in (dimension_column, metric_column):
        if col not in base_df.columns or col not in targ_df.columns:
            return {"error": f"Column '{col}' missing from baseline or target data."}

    base_grp = base_df.groupby(dimension_column)[metric_column].sum()
    targ_grp = targ_df.groupby(dimension_column)[metric_column].sum()

    combined = pd.DataFrame({"baseline": base_grp, "target": targ_grp}).fillna(0.0)
    combined["delta"] = combined["target"] - combined["baseline"]
    combined["pct_change"] = combined.apply(
        lambda r: round((r["delta"] / r["baseline"]) * 100, 2) if r["baseline"] != 0 else None,
        axis=1,
    )

    total_baseline = float(combined["baseline"].sum())
    total_target = float(combined["target"].sum())
    total_delta = total_target - total_baseline

    combined["contribution_to_change_pct"] = combined["delta"].apply(
        lambda d: round((d / total_delta) * 100, 2) if total_delta != 0 else 0.0
    )
    combined = combined.reindex(combined["delta"].abs().sort_values(ascending=False).index)

    drivers = [
        {
            "segment": str(seg),
            "baseline_value": round(float(r["baseline"]), 2),
            "target_value": round(float(r["target"]), 2),
            "delta": round(float(r["delta"]), 2),
            "pct_change": r["pct_change"],
            "contribution_to_total_change_pct": float(r["contribution_to_change_pct"]),
        }
        for seg, r in combined.iterrows()
    ]

    return {
        "dimension": dimension_column,
        "metric": metric_column,
        "total_baseline": round(total_baseline, 2),
        "total_target": round(total_target, 2),
        "total_delta": round(total_delta, 2),
        "total_pct_change": round((total_delta / total_baseline) * 100, 2) if total_baseline else None,
        "drivers": drivers,
    }