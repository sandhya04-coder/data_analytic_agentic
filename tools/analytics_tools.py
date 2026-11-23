from langchain_core.tools import tool
from analytics.metrics import compute_business_metrics
from analytics.trends import compute_trends
from analytics.anomalies import find_anomalies
from analytics.root_cause import decompose_change


@tool
def calculate_business_metrics(rows: list[dict], metric_columns: list[str] | None = None) -> dict:
    """Calculate deterministic totals, averages, medians, min/max, and top/bottom contributors."""
    return compute_business_metrics(rows=rows, metric_columns=metric_columns)


@tool
def analyze_trends(rows: list[dict], time_column: str, value_column: str) -> dict:
    """Identify period-over-period changes, peak/trough periods, and overall trend direction."""
    return compute_trends(rows=rows, time_column=time_column, value_column=value_column)


@tool
def detect_anomalies(
    rows: list[dict],
    value_column: str,
    label_column: str | None = None,
    z_threshold: float = 2.0,
) -> dict:
    """Detect statistical spikes or drops in numeric query results using Z-score and IQR."""
    return find_anomalies(
        rows=rows,
        value_column=value_column,
        label_column=label_column,
        z_threshold=z_threshold,
    )


@tool
def decompose_metric_change(
    baseline_rows: list[dict],
    target_rows: list[dict],
    dimension_column: str,
    metric_column: str,
) -> dict:
    """Decompose a KPI change between baseline and target periods across business segments."""
    return decompose_change(
        baseline_rows=baseline_rows,
        target_rows=target_rows,
        dimension_column=dimension_column,
        metric_column=metric_column,
    )