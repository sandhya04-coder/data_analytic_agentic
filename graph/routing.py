from langgraph.types import Send
from schemas.planning_schema import PlanningTaskType
from schemas.state import AnalyticsState


def route_after_intent(state: AnalyticsState) -> str:
    """Route to human clarification if needed, otherwise proceed to planning."""
    intent = state["intent"]
    if intent.needs_clarification and not state.get("clarification_response"):
        return "clarify_intent"
    return "planning_node"


def route_after_planning(state: AnalyticsState):
    """
    If the plan is blocked (e.g., out-of-range dates), skip SQL execution
    and jump straight to analysis/reporting with the documented limitations.
    Otherwise fan out executable tasks in parallel via LangGraph `Send`.
    """
    plan = state["plan"]
    executable_tasks = [
        t for t in plan.tasks if t.task_type != PlanningTaskType.DATA_DISCOVERY
    ]

    if not plan.is_executable or not executable_tasks:
        return "blocked_plan_node"

    return [
        Send(
            "sql_task_worker",
            {
                "question": state["question"],
                "intent": state["intent"],
                "plan": plan,
                "active_task": task,
            },
        )
        for task in executable_tasks
    ]