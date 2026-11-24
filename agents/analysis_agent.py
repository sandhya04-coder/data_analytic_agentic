import json
import pandas as pd
from config.llm_config import generate_structured
from prompts.analysis_agent_prompt import ANALYSIS_AGENT_SYSTEM_PROMPT
from schemas.intent_schema import BusinessIntent, AnalysisType
from schemas.planning_schema import AnalysisPlan
from schemas.sql_schema import SQLAgentOutput
from schemas.analysis_schema import AnalysisNarrative, AnalysisOutput
from tools.analytics_tools import (
    calculate_business_metrics,
    analyze_trends,
    detect_anomalies,
    decompose_metric_change,
)


class AnalysisAgent:
    """
    Agent 4: Runs deterministic Pandas/statistical analytics tools on
    SQL execution results and synthesizes a validated AnalysisOutput.
    """

    def _detect_columns(self, rows: list[dict]) -> tuple[str | None, list[str], list[str]]:
        """Infer time column, numeric KPI columns, and categorical label columns."""
        if not rows:
            return None, [], []
        df = pd.DataFrame(rows)
        numeric_cols = [
            c for c in df.select_dtypes(include="number").columns
            if not c.lower().endswith("id")
        ]
        non_numeric = [c for c in df.columns if c not in df.select_dtypes(include="number").columns]
        time_keywords = ("date", "month", "year", "quarter", "week", "period", "day")
        time_col = next((c for c in non_numeric if any(k in c.lower() for k in time_keywords)), None)
        label_cols = [c for c in non_numeric if c != time_col]
        return time_col, numeric_cols, label_cols

    def _run_deterministic_tools(
        self, sql_output: SQLAgentOutput, intent: BusinessIntent
    ) -> dict:
        """Execute relevant deterministic analytics tools across successful task results."""
        computed: dict = {
            "metric_calculations": {},
            "trend_analysis": {},
            "anomalies_detected": [],
            "root_cause_drivers": [],
        }

        successful_execs = [e for e in sql_output.executions if e.success and e.rows]

        for exec_res in successful_execs:
            task_key = exec_res.task_id
            rows = exec_res.rows
            time_col, numeric_cols, label_cols = self._detect_columns(rows)

            # 1. Always compute summary metrics
            metrics_res = calculate_business_metrics.invoke({
                "rows": rows,
                "metric_columns": numeric_cols or None,
            })
            computed["metric_calculations"][task_key] = metrics_res

            # 2. Trend analysis when time dimension + numeric KPI exist
            if time_col and numeric_cols:
                trend_res = analyze_trends.invoke({
                    "rows": rows,
                    "time_column": time_col,
                    "value_column": numeric_cols[0],
                })
                if "error" not in trend_res:
                    computed["trend_analysis"][task_key] = trend_res

            # 3. Anomaly detection when requested or enough rows exist
            if numeric_cols and (
                AnalysisType.ANOMALY_DETECTION in intent.analysis_types or len(rows) >= 6
            ):
                label_col = time_col or (label_cols[0] if label_cols else None)
                anom_res = detect_anomalies.invoke({
                    "rows": rows,
                    "value_column": numeric_cols[0],
                    "label_column": label_col,
                })
                for item in anom_res.get("anomalies", []):
                    computed["anomalies_detected"].append({"task_id": task_key, **item})

        # 4. Root-cause / period decomposition when two comparison tasks share dimension & metric
        if len(successful_execs) >= 2 and (
            intent.investigation_required or intent.requires_period_comparison
        ):
            base_exec, targ_exec = successful_execs[0], successful_execs[1]
            _, num_cols, lbl_cols = self._detect_columns(base_exec.rows)
            if num_cols and lbl_cols and set(lbl_cols + num_cols).issubset(set(targ_exec.columns)):
                decomp = decompose_metric_change.invoke({
                    "baseline_rows": base_exec.rows,
                    "target_rows": targ_exec.rows,
                    "dimension_column": lbl_cols[0],
                    "metric_column": num_cols[0],
                })
                if "drivers" in decomp:
                    computed["root_cause_drivers"] = decomp["drivers"]

        return computed

    def analyze(
        self,
        intent: BusinessIntent,
        plan: AnalysisPlan,
        sql_output: SQLAgentOutput,
    ) -> AnalysisOutput:
        """Analyze executed SQL results and return a validated AnalysisOutput."""
        successful_execs = [e for e in sql_output.executions if e.success]

        if not plan.is_executable or not successful_execs:
            caveats = list(plan.data_limitations) + list(sql_output.generation.generation_errors)
            return AnalysisOutput(
                original_question=intent.original_question,
                executive_summary=(
                    "The requested analysis could not be completed due to data availability or query execution constraints."
                ),
                data_caveats=caveats or ["No query results were returned."],
                is_successful=False,
            )

        deterministic = self._run_deterministic_tools(sql_output, intent)

        # Deduplicate identical query outputs to keep LLM context compact
        seen_queries = set()
        query_summaries = []
        for ex in successful_execs:
            if ex.query in seen_queries:
                continue
            seen_queries.add(ex.query)
            query_summaries.append({
                "task_id": ex.task_id,
                "row_count": ex.row_count,
                "truncated": ex.truncated,
                "rows": ex.rows[:100],
            })

        planned_tasks_json = json.dumps([t.model_dump() for t in plan.tasks], indent=2, default=str)
        prompt_payload = (
            f"ORIGINAL QUESTION: {intent.original_question}\n\n"
            f"BUSINESS INTENT:\n{intent.model_dump_json(indent=2)}\n\n"
            f"PLANNED TASKS:\n{planned_tasks_json}\n\n"
            f"DATA LIMITATIONS:\n{json.dumps(plan.data_limitations)}\n\n"
            f"SQL RESULTS:\n{json.dumps(query_summaries, indent=2, default=str)}\n\n"
            f"DETERMINISTIC ANALYTICS CALCULATIONS:\n{json.dumps(deterministic, indent=2, default=str)}\n\n"
            "Synthesize the structured AnalysisNarrative."
        )

        narrative: AnalysisNarrative = generate_structured(
            AnalysisNarrative,
            [("user", prompt_payload)],
            system_prompt=ANALYSIS_AGENT_SYSTEM_PROMPT,
        )

        return AnalysisOutput(
            original_question=intent.original_question,
            executive_summary=narrative.executive_summary,
            findings=narrative.findings,
            metric_calculations=deterministic["metric_calculations"],
            trend_analysis=deterministic["trend_analysis"],
            anomalies_detected=deterministic["anomalies_detected"],
            root_cause_drivers=deterministic["root_cause_drivers"],
            data_caveats=narrative.data_caveats,
            is_successful=True,
        )