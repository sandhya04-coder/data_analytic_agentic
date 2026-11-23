import json
from agents.intent_agent import IntentUnderstandingAgent
from agents.planning_agent import PlanningAgent
from agents.sql_agent import SQLGenerationAgent
from agents.analysis_agent import AnalysisAgent

q = "Top 5 products by revenue in 2017"

print("=" * 70)
print("1. INTENT UNDERSTANDING AGENT")
print("=" * 70)
intent = IntentUnderstandingAgent().understand(q)
print(intent.model_dump_json(indent=2))

print("\n" + "=" * 70)
print("2. PLANNING AGENT")
print("=" * 70)
planner = PlanningAgent()
plan = planner.plan(intent)
planner.close()
print(f"Executable: {plan.is_executable} | Tasks count: {len(plan.tasks)}")
for t in plan.tasks:
    print(f"  - {t.task_id} ({t.task_type.value}): {t.objective}")
if plan.data_limitations:
    print("Limitations:", plan.data_limitations)

print("\n" + "=" * 70)
print("3. SQL GENERATION AGENT")
print("=" * 70)
sql_out = SQLGenerationAgent().run(plan, intent)
for e in sql_out.executions:
    print(f"Task: {e.task_id} | Success: {e.success} | Attempts: {e.attempts} | Rows: {e.row_count}")
    print(f"SQL: {e.query}")
    print(f"Rows: {e.rows}\n")

print("=" * 70)
print("4. ANALYSIS AGENT")
print("=" * 70)
analysis = AnalysisAgent().analyze(intent, plan, sql_out)
print("EXECUTIVE SUMMARY:\n", analysis.executive_summary)
print("\nFINDINGS:")
for f in analysis.findings:
    print(f"- [{f.category.value}] {f.headline}: {f.detail}")
print("\nMETRICS:", json.dumps(analysis.metric_calculations, indent=2))