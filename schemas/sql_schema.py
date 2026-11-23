
from pydantic import BaseModel, Field, model_validator


class GeneratedSQLQuery(BaseModel):
    task_id: str = Field(
        description="ID of the corresponding Planning Agent task."
    )

    query: str = Field(
        description="Generated SQL query for the analytical task."
    )

    explanation: str = Field(
        description="Explanation of what the SQL query accomplishes."
    )

    tables_used: list[str] = Field(
        default_factory=list,
        description="Database tables referenced in the query."
    )


class SQLGenerationResult(BaseModel):
    original_question: str = Field(
        description="Original user business question."
    )

    queries: list[GeneratedSQLQuery] = Field(
        default_factory=list,
        description="SQL queries generated for the analysis plan."
    )

    generation_errors: list[str] = Field(
        default_factory=list,
        description="Errors encountered while generating SQL queries."
    )

    is_successful: bool = Field(
        default=True,
        description="Whether SQL generation completed successfully."
    )

    @model_validator(mode="after")
    def validate_result(self):

        task_ids = [
            query.task_id for query in self.queries
        ]

        if len(task_ids) != len(set(task_ids)):
            raise ValueError(
                "Each task must have at most one generated SQL query."
            )

        if self.is_successful and self.generation_errors:
            raise ValueError(
                "A successful result cannot contain generation errors."
            )

        return self

class SQLDraft(BaseModel):
    """What the LLM returns for one task (task_id is set by code)."""
    query: str = Field(description="A single read-only SQLite SELECT query.")
    explanation: str = Field(description="What the query does and why.")
    tables_used: list[str] = Field(default_factory=list)


class QueryExecutionResult(BaseModel):
    task_id: str
    query: str = ""
    success: bool
    columns: list[str] = Field(default_factory=list)
    rows: list[dict] = Field(default_factory=list)
    row_count: int = 0
    truncated: bool = False
    attempts: int = 1
    error: str | None = None


class SQLAgentOutput(BaseModel):
    generation: SQLGenerationResult
    executions: list[QueryExecutionResult]