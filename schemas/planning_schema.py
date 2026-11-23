
from enum import Enum
from pydantic import BaseModel, Field, model_validator


class PlanningTaskType(str, Enum):
    DATA_DISCOVERY = "data_discovery"
    DATA_EXTRACTION = "data_extraction"
    AGGREGATION = "aggregation"
    TREND_ANALYSIS = "trend_analysis"
    COMPARISON = "comparison"
    RANKING = "ranking"
    DISTRIBUTION = "distribution"
    ROOT_CAUSE_ANALYSIS = "root_cause_analysis"
    ANOMALY_DETECTION = "anomaly_detection"


class PlanningTask(BaseModel):
    task_id: str = Field(
        description="Unique identifier for this task."
    )

    task_type: PlanningTaskType = Field(
        description="Type of analytical task."
    )

    objective: str = Field(
        description="What this task must accomplish."
    )

    relevant_tables: list[str] = Field(
        default_factory=list,
        description="Database tables required for this task."
    )

    required_columns: list[str] = Field(
        default_factory=list,
        description="Required columns in table.column format."
    )

    metrics: list[str] = Field(
        default_factory=list,
        description="Business metrics needed for this task."
    )

    dimensions: list[str] = Field(
        default_factory=list,
        description="Dimensions used for grouping or analysis."
    )

    depends_on: list[str] = Field(
        default_factory=list,
        description="IDs of tasks that must finish first."
    )

    parallelizable: bool = Field(
        default=False,
        description="Whether this task can run independently."
    )

    expected_output: str = Field(
        description="Expected result or output of this task."
    )


class AnalysisPlan(BaseModel):
    original_question: str = Field(
        description="Original user question."
    )

    overall_objective: str = Field(
        description="Overall objective of the execution plan."
    )

    selected_tables: list[str] = Field(
        description="Database tables selected for the analysis."
    )

    tasks: list[PlanningTask] = Field(
        min_length=1,
        description="Ordered analytical tasks."
    )

    execution_strategy: str = Field(
        description="How tasks should be coordinated and executed."
    )

    data_limitations: list[str] = Field(
        default_factory=list,
        description="Missing or unavailable data relevant to the request."
    )
    is_executable: bool = True

    @model_validator(mode="after")
    def validate_plan(self):
        task_ids = [task.task_id for task in self.tasks]

        if len(task_ids) != len(set(task_ids)):
            raise ValueError("Task IDs must be unique.")

        task_id_set = set(task_ids)

        for task in self.tasks:
            if task.task_id in task.depends_on:
                raise ValueError(
                    f"Task {task.task_id} cannot depend on itself."
                )

            unknown_dependencies = (
                set(task.depends_on) - task_id_set
            )

            if unknown_dependencies:
                raise ValueError(
                    f"Task {task.task_id} has unknown dependencies: "
                    f"{unknown_dependencies}"
                )

        if not set(
            table for task in self.tasks
            for table in task.relevant_tables
        ).issubset(set(self.selected_tables)):
            raise ValueError(
                "Every task's relevant tables must appear "
                "in selected_tables."
            )

        return self
