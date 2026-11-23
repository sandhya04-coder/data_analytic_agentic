from schemas.planning_schema import (
    AnalysisPlan,
    PlanningTask,
    PlanningTaskType
)

task = PlanningTask(
    task_id="task_1",
    task_type=PlanningTaskType.DATA_EXTRACTION,
    objective="Retrieve order data.",
    relevant_tables=["Orders"],
    required_columns=["Orders.OrderID", "Orders.OrderDate"],
    metrics=["revenue"],
    dimensions=["month"],
    expected_output="Order data for revenue analysis."
)

plan = AnalysisPlan(
    original_question="Show monthly revenue trends.",
    overall_objective="Analyze monthly revenue.",
    selected_tables=["Orders"],
    tasks=[task],
    execution_strategy="Sequential execution."
)

print(plan.model_dump_json(indent=4))