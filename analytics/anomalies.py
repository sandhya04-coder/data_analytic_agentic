import pandas as pd


def find_anomalies(rows: list[dict], value_column: str, label_column: str | None = None, z_threshold: float = 2.0) -> dict:
    """Detect statistical outliers using Z-score and IQR methods."""
    if not rows:
        return {"anomalies": [], "note": "No rows provided."}

    df = pd.DataFrame(rows)
    if value_column not in df.columns:
        return {"error": f"Column '{value_column}' not found."}

    df[value_column] = pd.to_numeric(df[value_column], errors="coerce")
    df = df.dropna(subset=[value_column]).reset_index(drop=True)

    if len(df) < 4:
        return {"anomalies": [], "note": "Fewer than 4 data points; outlier detection skipped."}

    mean = float(df[value_column].mean())
    std = float(df[value_column].std(ddof=0))
    q1 = float(df[value_column].quantile(0.25))
    q3 = float(df[value_column].quantile(0.75))
    iqr = q3 - q1
    lower_fence = q1 - 1.5 * iqr
    upper_fence = q3 + 1.5 * iqr

    anomalies = []
    for idx, row in df.iterrows():
        val = float(row[value_column])
        z_score = ((val - mean) / std) if std > 0 else 0.0
        is_iqr_outlier = (val < lower_fence or val > upper_fence) and iqr > 0
        is_z_outlier = abs(z_score) >= z_threshold

        if is_z_outlier or is_iqr_outlier:
            label = str(row[label_column]) if (label_column and label_column in df.columns) else f"row_{idx}"
            anomalies.append({
                "label": label,
                "value": round(val, 2),
                "z_score": round(z_score, 2),
                "direction": "spike" if val > mean else "drop",
                "baseline_mean": round(mean, 2),
            })

    return {
        "value_column": value_column,
        "baseline_mean": round(mean, 2),
        "baseline_std": round(std, 2),
        "anomaly_count": len(anomalies),
        "anomalies": anomalies,
    }