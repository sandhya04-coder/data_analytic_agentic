
from schemas.intent_schema import (
    BusinessIntent,
    BusinessDomain,
    AnalysisType,
    TimeRequirement,
    TimeGranularity,
    ComparisonRequirement
)


intent = BusinessIntent(

    original_question=(
        "Why did our revenue decline in the last quarter?"
    ),

    business_domain=BusinessDomain.SALES,

    business_objective=(
        "Investigate the factors responsible for "
        "the decline in revenue."
    ),

    metrics=[
        "revenue",
        "order_count",
        "quantity_sold",
        "average_order_value"
    ],

    dimensions=[
        "product",
        "category",
        "customer",
        "country"
    ],

    time_requirement=TimeRequirement(
        relative_period="last quarter",
        granularity=TimeGranularity.MONTH
    ),

    comparison=ComparisonRequirement(
        comparison_type="quarter_over_quarter",
        baseline_period="previous quarter",
        target_period="last quarter"
    ),

    requires_period_comparison=True,

    analysis_types=[
        AnalysisType.COMPARISON,
        AnalysisType.TREND,
        AnalysisType.ROOT_CAUSE
    ],

    investigation_required=True,

    investigation_dimensions=[
        "product",
        "category",
        "customer",
        "country"
    ],

    requires_aggregation=True,

    requires_visualization=True,

    needs_clarification=False
)


print("ROOT CAUSE INTENT VALIDATED SUCCESSFULLY!")

print(intent.model_dump_json(indent=4))
