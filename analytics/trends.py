import pandas as pd


def compute_trends(rows: list[dict], time_column: str, value_column: str) -> dict:
    """Compute period-over-period changes, overall growth, and trend direction."""
    if not rows:
        return {"error": "No rows provided for trend analysis."}

    df = pd.DataFrame(rows)
    if time_column not in df.columns or value_column not in df.columns:
        return {"error": f"Missing required columns: {time_column} or {value_column}."}

    df = df[[time_column, value_column]].dropna().sort_values(by=time_column).reset_index(drop=True)
    df[value_column] = pd.to_numeric(df[value_column], errors="coerce")
    df = df.dropna()

    if len(df) < 2:
        return {"periods": len(df), "note": "At least 2 periods are required for trend calculation."}

    df["prev_value"] = df[value_column].shift(1)
    df["abs_change"] = df[value_column] - df["prev_value"]
    df["pct_change"] = ((df["abs_change"] / df["prev_value"]) * 100).round(2)

    first_val = float(df[value_column].iloc[0])
    last_val = float(df[value_column].iloc[-1])
    overall_pct = round(((last_val - first_val) / first_val) * 100, 2) if first_val else None

    if overall_pct is not None:
        direction = "upward" if overall_pct > 2 else ("downward" if overall_pct < -2 else "flat")
    else:
        direction = "undetermined"

    peak_idx = df[value_column].idxmax()
    trough_idx = df[value_column].idxmin()

    period_series = [
        {
            "period": str(row[time_column]),
            "value": round(float(row[value_column]), 2),
            "pct_change": None if pd.isna(row["pct_change"]) else float(row["pct_change"]),
        }
        for _, row in df.iterrows()
    ]

    return {
        "time_column": time_column,
        "value_column": value_column,
        "periods_count": int(len(df)),
        "direction": direction,
        "start_period": str(df[time_column].iloc[0]),
        "end_period": str(df[time_column].iloc[-1]),
        "start_value": round(first_val, 2),
        "end_value": round(last_val, 2),
        "overall_change_pct": overall_pct,
        "peak": {"period": str(df.loc[peak_idx, time_column]), "value": round(float(df.loc[peak_idx, value_column]), 2)},
        "trough": {"period": str(df.loc[trough_idx, time_column]), "value": round(float(df.loc[trough_idx, value_column]), 2)},
        "period_over_period": period_series,
    }