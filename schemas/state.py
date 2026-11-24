import operator
from typing import Annotated, Any, TypedDict
from schemas.intent_schema import BusinessIntent
from schemas.planning_schema import AnalysisPlan, PlanningTask
from schemas.sql_schema import GeneratedSQLQuery, QueryExecutionResult, SQLAgentOutput
from schemas.analysis_schema import AnalysisOutput
from schemas.reporting_schema import ExecutiveReport


class AnalyticsState(TypedDict, total=False):
    # Input & human-in-the-loop clarification
    question: str
    prior_context: str | None
    clarification_response: str | None

    # Agent 1 output
    intent: BusinessIntent

    # Agent 2 output
    plan: AnalysisPlan

    # Parallel SQL branch inputs/outputs (merged via operator.add)
    active_task: PlanningTask
    parallel_queries: Annotated[list[GeneratedSQLQuery], operator.add]
    parallel_executions: Annotated[list[QueryExecutionResult], operator.add]
    parallel_errors: Annotated[list[str], operator.add]

    # Assembled Agent 3 output
    sql_output: SQLAgentOutput

    # Agent 4 output
    analysis: AnalysisOutput

    # Agent 5 output
    report: ExecutiveReport

    # Execution trace for UI visibility
    trace_log: Annotated[list[dict[str, Any]], operator.add]