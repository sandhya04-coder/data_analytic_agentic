
from config.llm_config import generate_structured
from config.settings import MAX_SQL_RETRIES
from database.schema_inspector import SchemaInspector
from prompts.sql_agent_prompt import SQL_AGENT_SYSTEM_PROMPT
from schemas.intent_schema import BusinessIntent
from schemas.planning_schema import AnalysisPlan, PlanningTask, PlanningTaskType
from schemas.sql_schema import (
    SQLDraft, GeneratedSQLQuery, SQLGenerationResult,
    QueryExecutionResult, SQLAgentOutput
)
from tools.sql_tools import run_query, explain_query


class SQLGenerationAgent:
    """
    Agent 3: Generates, validates, explains, executes and,
    when needed, corrects SQL for every task in an AnalysisPlan.
    """

    def __init__(self, max_retries: int = MAX_SQL_RETRIES):
        self.max_retries = max_retries


    # ---------- helpers ----------

    def _schema_text(self, tables: list[str]) -> str:
        self.full_schema = SchemaInspector().get_complete_schema()
        lines = []
        for table in tables:
            info = self.full_schema.get(table)
            if not info:
                continue
            cols = ", ".join(f'{c["name"]} {c["type"]}' for c in info["columns"])
            fks = "; ".join(
                f'{fk["columns"]} -> {fk["referenced_table"]}{fk["referenced_columns"]}'
                for fk in info["foreign_keys"]
            )
            lines.append(f'TABLE "{table}": {cols}\n  PK: {info["primary_keys"]}  FK: {fks or "none"}')
        return "\n".join(lines)

    def _build_context(self, task: PlanningTask, plan: AnalysisPlan,
                       intent: BusinessIntent) -> str:
        tables = task.relevant_tables or plan.selected_tables
        return (
            f"ORIGINAL QUESTION: {plan.original_question}\n\n"
            f"TASK:\n{task.model_dump_json(indent=2)}\n\n"
            f"INTENT (filters, time, limits):\n{intent.model_dump_json(indent=2)}\n\n"
            f"DATA LIMITATIONS:\n{plan.data_limitations}\n\n"
            f"SCHEMA:\n{self._schema_text(tables)}\n\n"
            "Write the SQLite query for this task."
        )

    # ---------- one task: generate -> validate -> explain -> execute -> correct ----------

    def _solve_task(self, task, plan, intent):
        messages = [("user", self._build_context(task, plan, intent))]
        last_error, last_query = None, ""

        for attempt in range(1, self.max_retries + 2):
            try:
                draft: SQLDraft = generate_structured(
                    SQLDraft, messages, system_prompt=SQL_AGENT_SYSTEM_PROMPT
                )
            except Exception as error:
                last_error = f"LLM generation failed: {error}"
                continue

            last_query = draft.query.strip().rstrip(";")

            checks = explain_query(last_query)          # pre-flight: syntax + columns
            result = run_query(last_query) if checks["success"] else checks

            if result["success"]:
                generated = GeneratedSQLQuery(
                    task_id=task.task_id, query=last_query,
                    explanation=draft.explanation, tables_used=draft.tables_used,
                )
                execution = QueryExecutionResult(
                    task_id=task.task_id, query=last_query, success=True,
                    columns=result["columns"], rows=result["rows"],
                    row_count=result["row_count"], truncated=result["truncated"],
                    attempts=attempt,
                )
                return generated, execution, None

            last_error = result["error"]
            # Deterministic RBAC block: fail fast on attempt 1 without wasting LLM retries
            if last_error and "RBAC Access Denied" in last_error:
                break
            messages.append(("model", draft.model_dump_json()))
            messages.append(("user",
                f"That query failed ({result.get('error_type')}): {last_error}\n"
                "Return a corrected query."
            ))

        execution = QueryExecutionResult(
            task_id=task.task_id, query=last_query, success=False,
            attempts=self.max_retries + 1, error=last_error,
        )
        return None, execution, f"Task {task.task_id}: {last_error}"

    # ---------- public API ----------

    def run(self, plan: AnalysisPlan, intent: BusinessIntent) -> SQLAgentOutput:
        if not plan.is_executable:
            return SQLAgentOutput(
                generation=SQLGenerationResult(
                    original_question=plan.original_question,
                    queries=[],
                    generation_errors=plan.data_limitations or ["Plan is not executable."],
                    is_successful=False,
                ),
                executions=[],
            )

        queries, executions, errors = [], [], []

        for task in plan.tasks:
            if task.task_type == PlanningTaskType.DATA_DISCOVERY:
                continue        # discovery was already done by the Planning Agent
            generated, execution, error = self._solve_task(task, plan, intent)
            executions.append(execution)
            if generated:
                queries.append(generated)
            if error:
                errors.append(error)

        generation = SQLGenerationResult(
            original_question=plan.original_question,
            queries=queries,
            generation_errors=errors,
            is_successful=not errors,
        )
        return SQLAgentOutput(generation=generation, executions=executions)