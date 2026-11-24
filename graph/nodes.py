import logging
import sys
import time
from langgraph.types import Command, interrupt
from agents.intent_agent import IntentUnderstandingAgent
from agents.planning_agent import PlanningAgent
from agents.analysis_agent import AnalysisAgent
from agents.reporting_agent import ReportingAgent
from schemas.sql_schema import SQLGenerationResult, SQLAgentOutput
from schemas.state import AnalyticsState

# Configure unbuffered ASCII terminal logger for live pipeline tracing
logger = logging.getLogger("langgraph_pipeline")
if not logger.handlers:
    _handler = logging.StreamHandler(sys.stderr)
    _handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)-7s | %(message)s", datefmt="%H:%M:%S"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

_intent_agent = IntentUnderstandingAgent()
_analysis_agent = AnalysisAgent()
_reporting_agent = ReportingAgent()


def intent_node(state: AnalyticsState) -> dict:
    t0 = time.perf_counter()
    question = state["question"]
    if state.get("clarification_response"):
        question = f"{question}\nUser clarification: {state['clarification_response']}"

    logger.info(f"[Agent 1: Intent] START | Question: {question!r}")
    try:
        intent = _intent_agent.understand(
            question,
            prior_context=state.get("prior_context") or "",
        )
    except Exception as exc:
        logger.error(f"[Agent 1: Intent] FAILED after {time.perf_counter() - t0:.2f}s | Error: {exc}")
        raise

    dt = time.perf_counter() - t0
    status = "clarification_needed" if intent.needs_clarification else "completed"
    logger.info(
        f"[Agent 1: Intent] DONE ({dt:.2f}s) | Status: {status} | Domain: {intent.business_domain.value} "
        f"| Types: {[a.value for a in intent.analysis_types]}"
    )
    return {
        "intent": intent,
        "trace_log": [
            {
                "stage": "Agent 1: Intent Understanding",
                "status": status,
                "detail": f"Domain: {intent.business_domain.value} | Types: {[a.value for a in intent.analysis_types]}",
            }
        ],
    }


def clarify_intent_node(state: AnalyticsState) -> Command:
    """Pause graph via LangGraph interrupt() to request missing detail from Streamlit UI."""
    intent = state["intent"]
    logger.info(f"[Interrupt: Clarification] PAUSED | Prompt: {intent.clarification_question!r}")
    user_reply = interrupt(
        {
            "type": "clarification_required",
            "question": intent.clarification_question,
        }
    )
    logger.info(f"[Interrupt: Clarification] RESUMED | Reply: {str(user_reply)!r}")
    return Command(
        update={"clarification_response": str(user_reply)},
        goto="intent_node",
    )


def planning_node(state: AnalyticsState) -> dict:
    t0 = time.perf_counter()
    logger.info("[Agent 2: Planning] START | Inspecting schema and building analysis plan...")
    planner = PlanningAgent()
    try:
        plan = planner.plan(state["intent"])
    except Exception as exc:
        logger.error(f"[Agent 2: Planning] FAILED after {time.perf_counter() - t0:.2f}s | Error: {exc}")
        raise
    finally:
        planner.close()

    dt = time.perf_counter() - t0
    task_ids = [t.task_id for t in plan.tasks]
    if plan.is_executable:
        logger.info(f"[Agent 2: Planning] DONE ({dt:.2f}s) | Executable: True | Tasks: {task_ids}")
    else:
        logger.warning(
            f"[Agent 2: Planning] BLOCKED ({dt:.2f}s) | Executable: False | Limitations: {plan.data_limitations}"
        )

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
    reasons = plan.data_limitations or ["Plan is not executable."]
    logger.warning(f"[Agent 3: SQL] SKIPPED | Reason: {reasons}")
    sql_out = SQLAgentOutput(
        generation=SQLGenerationResult(
            original_question=plan.original_question,
            queries=[],
            generation_errors=reasons,
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

    logger.info(
        f"[Agent 3: SQL Aggregation] DONE | Tasks: {len(executions)} | Success: {sql_out.generation.is_successful}"
    )
    for ex in executions:
        if ex.success:
            logger.info(
                f"  -> [{ex.task_id}] OK | Rows: {ex.row_count} | Attempts: {ex.attempts} | SQL: {ex.query}"
            )
        else:
            logger.warning(
                f"  -> [{ex.task_id}] FAILED | Attempts: {ex.attempts} | Error: {ex.error}"
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
    t0 = time.perf_counter()
    logger.info("[Agent 4: Analysis] START | Computing statistics and synthesizing findings...")
    try:
        analysis = _analysis_agent.analyze(
            intent=state["intent"],
            plan=state["plan"],
            sql_output=state["sql_output"],
        )
    except Exception as exc:
        logger.error(f"[Agent 4: Analysis] FAILED after {time.perf_counter() - t0:.2f}s | Error: {exc}")
        raise

    dt = time.perf_counter() - t0
    logger.info(
        f"[Agent 4: Analysis] DONE ({dt:.2f}s) | Successful: {analysis.is_successful} "
        f"| Findings: {len(analysis.findings)} | Anomalies: {len(analysis.anomalies_detected)} "
        f"| Drivers: {len(analysis.root_cause_drivers)}"
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
    t0 = time.perf_counter()
    logger.info("[Agent 5: Reporting] START | Selecting chart specs, rendering visuals, and exporting report...")
    try:
        report = _reporting_agent.generate_report(
            intent=state["intent"],
            sql_output=state["sql_output"],
            analysis=state["analysis"],
        )
    except Exception as exc:
        logger.error(f"[Agent 5: Reporting] FAILED after {time.perf_counter() - t0:.2f}s | Error: {exc}")
        raise

    dt = time.perf_counter() - t0
    chart_summary = [f"{c.chart_type}:{c.task_id}" for c in report.charts]
    logger.info(
        f"[Agent 5: Reporting] DONE ({dt:.2f}s) | Title: {report.report_title!r} "
        f"| KPIs: {len(report.headline_kpis)} | Charts: {chart_summary} | Exported: {bool(report.report_file_path)}"
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