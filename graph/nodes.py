from langgraph.types import Command, interrupt
from agents.intent_agent import IntentUnderstandingAgent
from agents.planning_agent import PlanningAgent
from agents.analysis_agent import AnalysisAgent
from agents.reporting_agent import ReportingAgent
from schemas.sql_schema import SQLGenerationResult, SQLAgentOutput
from schemas.state import AnalyticsState

_intent_agent = IntentUnderstandingAgent()
_analysis_agent = AnalysisAgent()
_reporting_agent = ReportingAgent()


def intent_node(state: AnalyticsState) -> dict:
    question = state["question"]
    if state.get("clarification_response"):
        question = f"{question}\nUser clarification: {state['clarification_response']}"

    intent = _intent_agent.understand(question)
    return {
        "intent": intent,
        "trace_log": [
            {
                "stage": "Agent 1: Intent Understanding",
                "status": "clarification_needed" if intent.needs_clarification else "completed",
                "detail": f"Domain: {intent.business_domain.value} | Types: {[a.value for a in intent.analysis_types]}",
            }
        ],
    }


def clarify_intent_node(state: AnalyticsState) -> Command:
    """Pause graph via LangGraph interrupt() to request missing detail from Streamlit UI."""
    intent = state["intent"]
    user_reply = interrupt(
        {
            "type": "clarification_required",
            "question": intent.clarification_question,
        }
    )
    return Command(
        update={"clarification_response": str(user_reply)},
        goto="intent_node",
    )


def planning_node(state: AnalyticsState) -> dict:
    planner = PlanningAgent()
    try:
        plan = planner.plan(state["intent"])
    finally:
        planner.close()

    return {
        "plan": plan,
        "trace_log": [
            {
                "stage": "Agent 2: Planning",
                "status": "executable" if plan.is_executable else "blocked",
                "detail": f"Tasks planned: {len(plan.tasks)} | Limitations: {len(plan.data_limitations)}",
            }
        ],
    }


def blocked_plan_node(state: AnalyticsState) -> dict:
    plan = state["plan"]
    sql_out = SQLAgentOutput(
        generation=SQLGenerationResult(
            original_question=plan.original_question,
            queries=[],
            generation_errors=plan.data_limitations or ["Plan is not executable."],
            is_successful=False,
        ),
        executions=[],
    )
    return {
        "sql_output": sql_out,
        "trace_log": [
            {
                "stage": "Agent 3: SQL Generation",
                "status": "skipped",
                "detail": "Skipped because data availability checks blocked execution.",
            }
        ],
    }


def aggregate_sql_node(state: AnalyticsState) -> dict:
    """Join parallel SQL branches into a single validated SQLAgentOutput."""
    plan = state["plan"]
    queries = state.get("parallel_queries", [])
    executions = state.get("parallel_executions", [])
    errors = state.get("parallel_errors", [])

    sql_out = SQLAgentOutput(
        generation=SQLGenerationResult(
            original_question=plan.original_question,
            queries=queries,
            generation_errors=errors,
            is_successful=len(errors) == 0 and len(queries) > 0,
        ),
        executions=executions,
    )
    return {
        "sql_output": sql_out,
        "trace_log": [
            {
                "stage": "Agent 3: SQL Aggregation",
                "status": "completed" if sql_out.generation.is_successful else "partial_or_failed",
                "detail": f"Executed {len(executions)} query task(s).",
            }
        ],
    }


def analysis_node(state: AnalyticsState) -> dict:
    analysis = _analysis_agent.analyze(
        intent=state["intent"],
        plan=state["plan"],
        sql_output=state["sql_output"],
    )
    return {
        "analysis": analysis,
        "trace_log": [
            {
                "stage": "Agent 4: Business Analysis",
                "status": "completed" if analysis.is_successful else "blocked",
                "detail": f"Findings generated: {len(analysis.findings)}",
            }
        ],
    }


def reporting_node(state: AnalyticsState) -> dict:
    report = _reporting_agent.generate_report(
        intent=state["intent"],
        sql_output=state["sql_output"],
        analysis=state["analysis"],
    )
    return {
        "report": report,
        "trace_log": [
            {
                "stage": "Agent 5: Executive Reporting",
                "status": "completed",
                "detail": f"Charts: {len(report.charts)} | Report saved: {bool(report.report_file_path)}",
            }
        ],
    }