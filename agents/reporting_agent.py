import json
from config.llm_config import generate_structured
from prompts.reporting_agent_prompt import REPORTING_AGENT_SYSTEM_PROMPT
from reporting.charts import build_visual_suite
from schemas.intent_schema import BusinessIntent
from schemas.sql_schema import SQLAgentOutput
from schemas.analysis_schema import AnalysisOutput
from schemas.reporting_schema import ChartArtifact, ReportNarrative, ExecutiveReport
from tools.reporting_tools import export_business_report


class ReportingAgent:
    """
    Agent 5: Generates a multi-chart Plotly visual suite, synthesizes an executive brief,
    and exports both Markdown and self-contained interactive HTML reports.
    """

    def generate_report(
        self,
        intent: BusinessIntent,
        sql_output: SQLAgentOutput,
        analysis: AnalysisOutput,
    ) -> ExecutiveReport:
        charts: list[ChartArtifact] = []

        # 1. Generate multi-chart visual suite (Comparison/Trend + Heatmap + Treemap + Period Bar + Pareto)
        if analysis.is_successful and len(sql_output.executions) >= 1:
            seen_queries = set()
            for ex in sql_output.executions:
                if not ex.success or len(ex.rows) < 2 or ex.query in seen_queries:
                    continue
                seen_queries.add(ex.query)

                suite = build_visual_suite(
                    rows=ex.rows,
                    title=intent.original_question,
                    task_id=ex.task_id,
                )
                for ch in suite:
                    charts.append(
                        ChartArtifact(
                            task_id=ch["task_id"],
                            chart_type=ch["chart_type"],
                            title=ch["title"],
                            html_path=ch["html_path"],
                            figure_json=ch["figure_json"],
                        )
                    )

        # 2. Synthesize executive brief via Gemini (1 LLM call)
        sample_rows = [
            {
                "task_id": ex.task_id,
                "top_rows": ex.rows[:12],
                "bottom_rows": ex.rows[-5:] if len(ex.rows) > 12 else [],
            }
            for ex in sql_output.executions
            if ex.success
        ]
        prompt_payload = (
            f"ORIGINAL QUESTION: {intent.original_question}\n\n"
            f"ANALYSIS OUTPUT:\n{analysis.model_dump_json(indent=2)}\n\n"
            f"QUERY DATA HIGHLIGHTS:\n{json.dumps(sample_rows, indent=2)}\n\n"
            "Generate the structured ReportNarrative."
        )

        narrative: ReportNarrative = generate_structured(
            ReportNarrative,
            [("user", prompt_payload)],
            system_prompt=REPORTING_AGENT_SYSTEM_PROMPT,
        )

        # 3. Assemble & export final ExecutiveReport (.md + interactive .html with embedded charts)
        report = ExecutiveReport(
            original_question=intent.original_question,
            report_title=narrative.report_title,
            subtitle=narrative.subtitle,
            headline_kpis=narrative.headline_kpis,
            business_summary=narrative.business_summary,
            top_drivers=narrative.top_drivers,
            key_findings_summary=narrative.key_findings_summary,
            root_cause_section=narrative.root_cause_section,
            recommendations=narrative.recommendations,
            supporting_evidence_notes=narrative.supporting_evidence_notes,
            charts=charts,
            is_successful=analysis.is_successful,
            follow_up_questions=narrative.follow_up_questions,
        )

        exported = export_business_report.invoke({
            "report_data": report.model_dump(exclude={"report_file_path", "report_markdown", "report_html"})
        })
        if exported.get("success"):
            report.report_file_path = exported["report_file_path"]
            report.report_markdown = exported["report_markdown"]
            report.report_html = exported.get("report_html", "")

        return report