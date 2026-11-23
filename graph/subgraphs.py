from langgraph.graph import StateGraph, START, END
from agents.sql_agent import SQLGenerationAgent
from schemas.state import AnalyticsState

_sql_agent = SQLGenerationAgent()


def _execute_single_sql_task(state: AnalyticsState) -> dict:
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
    sub = StateGraph(AnalyticsState)
    sub.add_node("solve_sql_task", _execute_single_sql_task)
    sub.add_edge(START, "solve_sql_task")
    sub.add_edge("solve_sql_task", END)
    return sub.compile()