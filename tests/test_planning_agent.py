
from agents.planning_agent import PlanningAgent

from schemas.intent_schema import (
    BusinessIntent,
    BusinessDomain,
    AnalysisType,
    TimeRequirement,
    TimeGranularity
)


intent = BusinessIntent(
    original_question="Show monthly revenue trends for 1997.",

    business_domain=BusinessDomain.SALES,

    business_objective="Analyze monthly revenue trends for 1997.",

    metrics=["revenue"],

    dimensions=["month"],

    filters=[],

    time_requirement=TimeRequirement(
        start_date="1997-01-01",
        end_date="1997-12-31",
        granularity=TimeGranularity.MONTH
    ),

    comparison=None,

    requires_period_comparison=False,

    analysis_types=[
        AnalysisType.SUMMARY,
        AnalysisType.TREND
    ],

    investigation_required=False,

    investigation_dimensions=[],

    result_limit=None,

    sorting_preference=None,

    requires_aggregation=True,

    requires_visualization=True,

    needs_clarification=False,

    clarification_question=None
)


agent = PlanningAgent()

try:
    plan = agent.plan(intent)

    print("\nGENERATED ANALYSIS PLAN:\n")
    print(plan.model_dump_json(indent=4))

    print("\nPLANNING AGENT TEST PASSED")

finally:
    agent.close()
