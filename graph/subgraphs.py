import operator
from typing import Annotated, Any, TypedDict
from langgraph.graph import StateGraph, START, END
from agents.sql_agent import SQLGenerationAgent
from schemas.intent_schema import BusinessIntent
from schemas.planning_schema import AnalysisPlan, PlanningTask
from schemas.sql_schema import GeneratedSQLQuery, QueryExecutionResult

_sql_agent = SQLGenerationAgent()


class SQLWorkerInput(TypedDict):
    active_task: PlanningTask
    plan: AnalysisPlan
    intent: BusinessIntent


class SQLWorkerOutput(TypedDict):
    parallel_queries: Annotated[list[GeneratedSQLQuery], operator.add]
    parallel_executions: Annotated[list[QueryExecutionResult], operator.add]
    parallel_errors: Annotated[list[str], operator.add]
    trace_log: Annotated[list[dict[str, Any]], operator.add]


def _execute_single_sql_task(state: SQLWorkerInput) -> SQLWorkerOutput:
    """Subgraph node: generate, validate, explain, execute, and self-correct one SQL task."""
    task = state["active_task"]
    plan = state["plan"]
    intent = state["intent"]

    generated, execution, error = _sql_agent._solve_task(task, plan, intent)

    return {
        "parallel_queries": [generated] if generated else [],
        "parallel_executions": [execution],
        "parallel_errors": [error] if error else [],
        "trace_log": [
            {
                "stage": f"SQL Worker ({task.task_id})",
                "status": "success" if execution.success else "failed",
                "detail": f"Attempts: {execution.attempts} | Rows: {execution.row_count}",
            }
        ],
    }


def build_sql_worker_subgraph():
    """Modular subgraph for single-task SQL generation + self-correction."""
    sub = StateGraph(SQLWorkerOutput, input_schema=SQLWorkerInput, output_schema=SQLWorkerOutput)
    sub.add_node("solve_sql_task", _execute_single_sql_task)
    sub.add_edge(START, "solve_sql_task")
    sub.add_edge("solve_sql_task", END)
    return sub.compile()