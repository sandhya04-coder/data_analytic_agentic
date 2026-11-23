from agents.intent_agent import IntentUnderstandingAgent
from agents.planning_agent import PlanningAgent
from agents.sql_agent import SQLGenerationAgent

for q in [
    #"Top 5 products by revenue in 2010",   # Negative / out-of-range date test
    "Top 5 products by revenue in 2017",   # Positive / in-range test
]:
    print("=" * 60)
    print("QUESTION:", q)
    intent = IntentUnderstandingAgent().understand(q)
    planner = PlanningAgent()
    plan = planner.plan(intent)
    planner.close()

    print("Executable:", plan.is_executable)
    print("Limitations:", plan.data_limitations)

    out = SQLGenerationAgent().run(plan, intent)
    print("SQL Success:", out.generation.is_successful, "| Errors:", out.generation.generation_errors)

    for e in out.executions:
        print(e.task_id, e.success, f"attempts={e.attempts}", f"rows={e.row_count}", e.error)
        print(e.query)
        print("Sample rows:", e.rows[:3], "\n")