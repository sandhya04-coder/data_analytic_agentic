from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, START, END
from graph.nodes import (
    intent_node,
    clarify_intent_node,
    planning_node,
    blocked_plan_node,
    aggregate_sql_node,
    analysis_node,
    reporting_node,
)
from graph.routing import route_after_intent, route_after_planning
from graph.subgraphs import build_sql_worker_subgraph
from schemas.state import AnalyticsState


def build_analytics_graph():
    """Compile the full 5-agent LangGraph StateGraph with parallel SQL execution & checkpointing."""
    workflow = StateGraph(AnalyticsState)

    workflow.add_node("intent_node", intent_node)
    workflow.add_node("clarify_intent", clarify_intent_node)
    workflow.add_node("planning_node", planning_node)
    workflow.add_node("blocked_plan_node", blocked_plan_node)
    workflow.add_node("sql_task_worker", build_sql_worker_subgraph())
    workflow.add_node("aggregate_sql_node", aggregate_sql_node)
    workflow.add_node("analysis_node", analysis_node)
    workflow.add_node("reporting_node", reporting_node)

    workflow.add_edge(START, "intent_node")
    workflow.add_conditional_edges(
        "intent_node",
        route_after_intent,
        {
            "clarify_intent": "clarify_intent",
            "planning_node": "planning_node",
        },
    )
    workflow.add_conditional_edges(
        "planning_node",
        route_after_planning,
        ["sql_task_worker", "blocked_plan_node"],
    )
    workflow.add_edge("sql_task_worker", "aggregate_sql_node")
    workflow.add_edge("aggregate_sql_node", "analysis_node")
    workflow.add_edge("blocked_plan_node", "analysis_node")
    workflow.add_edge("analysis_node", "reporting_node")
    workflow.add_edge("reporting_node", END)

    checkpointer = MemorySaver()
    return workflow.compile(checkpointer=checkpointer)