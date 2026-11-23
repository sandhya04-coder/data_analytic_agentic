import json
from agents.analysis_agent import AnalysisAgent
from schemas.intent_schema import BusinessIntent, BusinessDomain, AnalysisType, TimeRequirement, TimeGranularity
from schemas.planning_schema import AnalysisPlan, PlanningTask, PlanningTaskType
from schemas.sql_schema import SQLAgentOutput, SQLGenerationResult, GeneratedSQLQuery, QueryExecutionResult

# Mock inputs from your previous Agents 1-3 run (0 LLM calls)
intent = BusinessIntent(
    original_question="Top 5 products by revenue in 2017",
    business_domain=BusinessDomain.SALES,
    business_objective="Identify the top 5 products based on revenue for the year 2017.",
    metrics=["revenue"],
    dimensions=["product"],
    time_requirement=TimeRequirement(
        start_date="2017-01-01",
        end_date="2017-12-31",
        granularity=TimeGranularity.YEAR,
    ),
    analysis_types=[AnalysisType.RANKING],
    result_limit=5,
    requires_aggregation=True,
    requires_visualization=True,
)

plan = AnalysisPlan(
    original_question=intent.original_question,
    overall_objective=intent.business_objective,
    selected_tables=["Orders", "Order Details", "Products"],
    tasks=[
        PlanningTask(
            task_id="top_5_products_2017",
            task_type=PlanningTaskType.RANKING,
            objective="Calculate total revenue per product for 2017 and rank top 5.",
            relevant_tables=["Orders", "Order Details", "Products"],
            expected_output="Top 5 products with total_revenue",
        )
    ],
    execution_strategy="Single ranking query",
    is_executable=True,
)

sql_out = SQLAgentOutput(
    generation=SQLGenerationResult(
        original_question=intent.original_question,
        queries=[
            GeneratedSQLQuery(
                task_id="top_5_products_2017",
                query='SELECT P.ProductName, SUM(OD.UnitPrice * OD.Quantity * (1 - OD.Discount)) AS total_revenue FROM "Order Details" AS OD JOIN Orders AS O ON OD.OrderID = O.OrderID JOIN Products AS P ON OD.ProductID = P.ProductID WHERE strftime(\'%Y\', O.OrderDate) = \'2017\' GROUP BY P.ProductID ORDER BY total_revenue DESC LIMIT 5',
                explanation="Top 5 products by 2017 revenue.",
                tables_used=["Orders", "Order Details", "Products"],
            )
        ],
        is_successful=True,
    ),
    executions=[
        QueryExecutionResult(
            task_id="top_5_products_2017",
            query='SELECT P.ProductName, SUM(OD.UnitPrice * OD.Quantity * (1 - OD.Discount)) AS total_revenue FROM "Order Details" AS OD JOIN Orders AS O ON OD.OrderID = O.OrderID JOIN Products AS P ON OD.ProductID = P.ProductID WHERE strftime(\'%Y\', O.OrderDate) = \'2017\' GROUP BY P.ProductID ORDER BY total_revenue DESC LIMIT 5',
            success=True,
            columns=["ProductName", "total_revenue"],
            rows=[
                {"ProductName": "Côte de Blaye", "total_revenue": 49198.085},
                {"ProductName": "Raclette Courdavault", "total_revenue": 35775.3},
                {"ProductName": "Thüringer Rostbratwurst", "total_revenue": 34755.913},
                {"ProductName": "Gnocchi di nonna Alice", "total_revenue": 32604.0},
                {"ProductName": "Manjimup Dried Apples", "total_revenue": 24570.8},
            ],
            row_count=5,
            attempts=1,
        )
    ],
)

analysis = AnalysisAgent().analyze(intent, plan, sql_out)

print("EXECUTIVE SUMMARY:\n", analysis.executive_summary)
print("\nFINDINGS:")
for f in analysis.findings:
    print(f"- [{f.category.value}] {f.headline} ({f.confidence})")
    print(f"  Detail: {f.detail}")
    print(f"  Metrics: {[m.model_dump() for m in f.supporting_metrics]}")
print("\nDETERMINISTIC METRICS:\n", json.dumps(analysis.metric_calculations, indent=2))