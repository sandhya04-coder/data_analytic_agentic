import uuid
import pandas as pd
import plotly.io as pio
import streamlit as st
from datetime import datetime
from langgraph.types import Command
from sqlalchemy import text
# Line 8: Import resolve_policy_for_user
from security.policy_guard import (
    SSO_USERS,
    get_policies_for_db,
    resolve_policy_for_user,
    set_active_policy,
)
from database.connection import (
    get_engine,
    get_table_names,
    list_available_databases,
    set_active_database,
)
from database.schema_inspector import SchemaInspector
from graph.workflow import build_analytics_graph

# ---------------------------------------------------------------------------
# Page Config & Custom Styling
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Enterprise BI • Multi-Agent Analytics Workbench",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .hero-banner {
        background: linear-gradient(135deg, #0f172a 0%, #1e3a8a 60%, #0ea5e9 100%);
        padding: 1.4rem 1.8rem;
        border-radius: 14px;
        color: #ffffff;
        margin-bottom: 1.2rem;
        box-shadow: 0 6px 20px rgba(15, 23, 42, 0.18);
    }
    .hero-banner h1 {
        margin: 0;
        font-size: 1.7rem;
        font-weight: 700;
        letter-spacing: -0.02em;
    }
    .hero-banner p {
        margin: 0.35rem 0 0 0;
        font-size: 0.95rem;
        color: #e0f2fe;
    }
    .rec-card {
        border-left: 4px solid #0284c7;
        background-color: #f8fafc;
        padding: 0.95rem 1.15rem;
        border-radius: 8px;
        margin-bottom: 0.75rem;
        color: #0f172a;
    }
    .rec-high { border-left-color: #dc2626; }
    .rec-medium { border-left-color: #d97706; }
    .rec-low { border-left-color: #16a34a; }
    .badge {
        display: inline-block;
        padding: 0.15rem 0.55rem;
        border-radius: 999px;
        font-size: 0.75rem;
        font-weight: 600;
        background: #e0f2fe;
        color: #0369a1;
        margin-right: 0.4rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

SAMPLE_PROMPTS_BY_DB = {
    "northwind": [
        "Top 5 products by revenue in 2017",
        "Monthly revenue trend across 2017 and 2018",
        "Why did revenue change between Q4 2017 and Q1 2018? Break down by category and region.",
        "Which customers generated the highest revenue overall, and how many orders did they place?",
    ],
    "olist": [
        "Top 10 product categories by total payment revenue",
        "Monthly order volume and revenue trend across 2017 and 2018",
        "Which customer states generated the highest revenue and average review score?",
        "Why did revenue change between Q4 2017 and Q1 2018? Break down by top product categories and customer states.",
    ],
}


# ---------------------------------------------------------------------------
# Cached Database & Graph Helpers
# ---------------------------------------------------------------------------
@st.cache_resource
def get_compiled_graph():
    return build_analytics_graph()


@st.cache_data(ttl=300)
def get_db_overview_stats(db_key: str, policy_id: str = "exec_admin") -> dict:
    engine = get_engine(db_key)
    inspector = SchemaInspector(db_key)
    tables = inspector.get_all_tables()
    schema = inspector.get_complete_schema()
    table_counts = {}
    detected_date_range = "Schema-driven"

    with engine.connect() as conn:
        for t in tables:
            quoted = engine.dialect.identifier_preparer.quote(t)
            cnt = conn.execute(text(f"SELECT COUNT(*) FROM {quoted}")).scalar_one()
            table_counts[t] = int(cnt)

        # Auto-detect the first date/timestamp column across any table in the active DB
        for t in tables:
            for col in schema.get(t, {}).get("columns", []):
                col_name = col["name"]
                col_type = str(col.get("type", "")).upper()
                if any(k in col_name.lower() for k in ("date", "timestamp", "time", "created")) or any(
                    dt in col_type for dt in ("DATE", "TIME")
                ):
                    q_tbl = engine.dialect.identifier_preparer.quote(t)
                    q_col = engine.dialect.identifier_preparer.quote(col_name)
                    res = conn.execute(
                        text(f"SELECT MIN({q_col}), MAX({q_col}) FROM {q_tbl} WHERE {q_col} IS NOT NULL")
                    ).first()
                    if res and res[0] is not None and res[1] is not None:
                        detected_date_range = f"{t}.{col_name}: {str(res[0])[:10]} → {str(res[1])[:10]}"
                        break
            if detected_date_range != "Schema-driven":
                break

    return {
        "tables": tables,
        "table_counts": table_counts,
        "total_rows": sum(table_counts.values()),
        "date_range": detected_date_range,
        "schema": schema,
        "relationships": inspector.get_table_relationships(),
    }


@st.cache_data(ttl=300)
def load_table_preview(db_key: str, table_name: str, limit: int = 25) -> pd.DataFrame:
    engine = get_engine(db_key)
    quoted = engine.dialect.identifier_preparer.quote(table_name)
    with engine.connect() as conn:
        return pd.read_sql(text(f"SELECT * FROM {quoted} LIMIT :lim"), conn, params={"lim": limit})


# ---------------------------------------------------------------------------
# Session State Initialization
# ---------------------------------------------------------------------------
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())
if "result_state" not in st.session_state:
    st.session_state.result_state = None
if "pending_clarification" not in st.session_state:
    st.session_state.pending_clarification = None
if "history" not in st.session_state:
    st.session_state.history = []
if "auto_run_question" not in st.session_state:
    st.session_state.auto_run_question = None
if "audit_log" not in st.session_state:
    st.session_state.audit_log = []
if "active_question" not in st.session_state:         
    st.session_state.active_question = ""

# ---------------------------------------------------------------------------
# Sidebar: Multi-Tenant Database Switcher, Pulse & Sample Prompts
# ---------------------------------------------------------------------------
available_dbs = list_available_databases()

with st.sidebar:
    st.markdown("###  Enterprise SSO Session")
    selected_email = st.selectbox(
        "Authenticated Identity",
        options=list(SSO_USERS.keys()),
        format_func=lambda e: f"{SSO_USERS[e].full_name} ({e})",
        key="sso_user_selector",
    )
    current_user = SSO_USERS[selected_email]
    if st.session_state.get("active_sso_email") != selected_email:
        st.session_state.active_sso_email = selected_email
        st.session_state.result_state = None
        st.session_state.pending_clarification = None
        st.session_state.active_question = ""
    # Line 154: Resolve user-specific claims instead of raw policy lookup
    selected_db = current_user.db_key
    active_policy = resolve_policy_for_user(current_user)

    set_active_database(selected_db)
    set_active_policy(active_policy)

    st.caption(f"**Role:** {current_user.title}")
    st.caption(f"**Bound Tenant DB:** `{selected_db}.sqlite` (isolated)")
    with st.expander("Decoded JWT & Security Claims", expanded=False):
        st.json(current_user.claims)
        if active_policy.row_filters:
            st.caption(f"**ABAC Row Filter:** `{active_policy.row_filters}`")
        if active_policy.allowed_tables is not None:
            st.caption(f"**RBAC Tables:** `{', '.join(sorted(active_policy.allowed_tables))}`")
        if active_policy.blocked_columns:
            st.caption(f"**Hidden Columns:** `{active_policy.blocked_columns}`")

    db_stats = get_db_overview_stats(selected_db, active_policy.policy_id)

    st.divider()
    st.markdown("### Quick Analytical Prompts")
    sample_prompts = SAMPLE_PROMPTS_BY_DB.get(
        selected_db,
        [f"Summarize total rows and key metrics across {db_stats['tables'][0]}"],
    )
    for idx, sp in enumerate(sample_prompts):
        if st.button(sp, key=f"sample_{selected_db}_{idx}", width="stretch"):
            st.session_state.auto_run_question = sp
            st.rerun()

    st.divider()
    if st.session_state.history:
        st.markdown("###  Recent Queries")
        for idx, item in enumerate(reversed(st.session_state.history[-5:]), 1):
            st.caption(f"{idx}. {item}")

# ---------------------------------------------------------------------------
# Hero Header & Query Input Bar
# ---------------------------------------------------------------------------
st.markdown(
    f"""
    <div class="hero-banner">
        <h1>{selected_db.title()} Autonomous Business Intelligence</h1>
        <p>5-Agent LangGraph Pipeline • Intent → Evidence-Based Planning → Self-Correcting SQL → Deterministic Analytics → Executive Reporting</p>
    </div>
    """,
    unsafe_allow_html=True,
)

queued_q = st.session_state.pop("auto_run_question", None)

with st.form("query_form", clear_on_submit=False):
    col_q, col_btn = st.columns([5, 1])
    user_question = col_q.text_input(
        f"Ask a business question about {selected_db.title()} data:",
        placeholder=f"e.g., {sample_prompts[0]}",
    )
    submitted = col_btn.form_submit_button("Analyze ", width="stretch")

# ---------------------------------------------------------------------------
# Graph Execution (New Query or Clarification Resume)
# ---------------------------------------------------------------------------
graph = get_compiled_graph()

if queued_q:
    active_question = queued_q.strip()
elif submitted and user_question.strip():
    active_question = user_question.strip()
else:
    active_question = ""

if active_question:
    st.session_state.active_question = active_question
    set_active_database(selected_db)
    set_active_policy(active_policy)
    st.session_state.thread_id = str(uuid.uuid4())
    st.session_state.pending_clarification = None
    config = {"configurable": {"thread_id": st.session_state.thread_id}}

    prior_context = ""
    if st.session_state.result_state and "report" in st.session_state.result_state:
        prev_q = st.session_state.result_state.get("question", "")
        prev_summary = st.session_state.result_state["report"].business_summary
        prior_context = f"Previous Question: {prev_q}\nPrevious Findings Summary: {prev_summary}"

    with st.status("Running 5-Agent LangGraph Workflow...", expanded=True) as status:
        st.write(" **Agent 1 & 2:** Understanding business intent & profiling database schema...")
        final_state = graph.invoke(
            {
                "question": active_question,
                "prior_context": prior_context,
                "trace_log": [],
            },
            config=config,
        )

        snapshot = graph.get_state(config)
        if snapshot.next:
            interrupt_payload = snapshot.tasks[0].interrupts[0].value
            st.session_state.pending_clarification = interrupt_payload.get(
                "question", "Could you clarify your request?"
            )
            status.update(label="Clarification needed from user", state="running")
        else:
            st.session_state.result_state = final_state
            st.session_state.history.append(f"[{current_user.email}] {active_question}")
            st.session_state.audit_log.append({
                "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "User": current_user.email,
                "Database": selected_db,
                "Role": active_policy.display_name,
                "Question": active_question,
                "Queries": len(final_state["sql_output"].executions),
                "Status": "Success" if final_state["report"].is_successful else "Blocked / Limited",
            })
            status.update(label="Analysis complete!", state="complete", expanded=False)

# Handle Human-in-the-Loop Clarification Interrupt
if st.session_state.pending_clarification:
    st.warning(f"**Clarification Needed:** {st.session_state.pending_clarification}")
    with st.form("clarify_form"):
        clarify_reply = st.text_input("Your clarification:")
        if st.form_submit_button("Resume Analysis"):
            set_active_database(selected_db)
            set_active_policy(active_policy)
            config = {"configurable": {"thread_id": st.session_state.thread_id}}
            with st.status("Resuming workflow...", expanded=True) as status:
                final_state = graph.invoke(Command(resume=clarify_reply), config=config)
                st.session_state.pending_clarification = None
                st.session_state.result_state = final_state
                status.update(label="Analysis complete!", state="complete", expanded=False)

# ---------------------------------------------------------------------------
# Main Workspace Tabs
#---------------------------------------------------------------------------
state = st.session_state.result_state

displayed_q = st.session_state.active_question or (state.get("question", "") if state else "")
if displayed_q:
    st.markdown(
        f"""
        <div style="
            background: #f1f5f9;
            border-left: 4px solid #0ea5e9;
            padding: 0.75rem 1.1rem;
            border-radius: 8px;
            margin: 0.4rem 0 1rem 0;
            color: #0f172a;
        ">
            <span style="font-size:0.75rem; font-weight:700; text-transform:uppercase; color:#0369a1; letter-spacing:0.04em;">
                Active Analytical Question
            </span><br/>
            <span style="font-size:1.05rem; font-weight:600;">{displayed_q}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
tab_report, tab_sql, tab_pipeline, tab_db = st.tabs(
    [
        " Executive Report & Charts",
        " SQL Queries & Data Audit",
        " Agent Pipeline & Reasoning",
        " Database Explorer",
    ]
)

# === TAB 1: EXECUTIVE REPORT & CHARTS ===
with tab_report:
    if not state or "report" not in state:
        st.info("Enter a business question above (or click a sample prompt in the sidebar) to generate an executive brief.")
    else:
        report = state["report"]
        analysis = state["analysis"]
        sql_out = state["sql_output"]

        st.markdown(f"## {report.report_title}")
        if getattr(report, "subtitle", ""):
            st.caption(report.subtitle)

        # 1. Dynamic Headline KPI Cards (fallback to execution stats if blocked)
        if getattr(report, "headline_kpis", None):
            kpi_cols = st.columns(len(report.headline_kpis))
            for col, kpi in zip(kpi_cols, report.headline_kpis):
                delta_color = "inverse" if kpi.sentiment == "negative" else "normal"
                col.metric(
                    label=kpi.label,
                    value=kpi.value,
                    delta=kpi.delta if kpi.delta else None,
                    delta_color=delta_color,
                )
        else:
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Status", "Completed" if report.is_successful else "Blocked / Limited")
            k2.metric("SQL Queries Run", len(sql_out.executions))
            k3.metric("Total Rows Analyzed", sum(e.row_count for e in sql_out.executions if e.success))
            k4.metric("Visualizations", len(report.charts))

        st.divider()

        # 2. Executive Summary
        st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)
        st.markdown("### Executive Summary")
        st.info(report.business_summary)

        # 3. Multi-Chart Visual Analytics Grid (Full-width for dense matrices, 2-col for compact views)
        if report.charts:
            st.markdown(f"### Visual Analytics Suite ({len(report.charts)} Interactive Views)")
            wide_types = {"bar", "heatmap", "line"}
            wide_charts = [c for c in report.charts if c.chart_type in wide_types and c.figure_json]
            grid_charts = [c for c in report.charts if c.chart_type not in wide_types and c.figure_json]

            for ch in wide_charts:
                with st.container(border=True):
                    st.plotly_chart(pio.from_json(ch.figure_json), width="stretch")

            for i in range(0, len(grid_charts), 2):
                row_charts = grid_charts[i : i + 2]
                cols = st.columns(len(row_charts))
                for col, ch in zip(cols, row_charts):
                    with col:
                        with st.container(border=True):
                            st.plotly_chart(pio.from_json(ch.figure_json), width="stretch")

        # 4. Segment Drivers & Risk Breakdown Table
        if getattr(report, "top_drivers", None):
            st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)
            st.markdown("### Segment Drivers & Risk Breakdown")
            drivers_df = pd.DataFrame([
                {
                    "Segment": d.segment,
                    "Classification": d.role,
                    "Performance / Delta": d.metric_value,
                    "Key Takeaway": d.takeaway,
                }
                for d in report.top_drivers
            ])
            st.dataframe(drivers_df, hide_index=True, width="stretch")

        # 5. Two-Column Layout: Key Findings & Root Cause
        col_f, col_rc = st.columns([1.15, 1]) if report.root_cause_section else (st.container(), None)
        with col_f:
            if report.key_findings_summary:
                st.markdown("### Key Findings")
                for item in report.key_findings_summary:
                    st.markdown(f"- {item}")

        if col_rc is not None and report.root_cause_section:
            with col_rc:
                st.markdown("### Root Cause & Driver Decomposition")
                st.markdown(report.root_cause_section)

        # 6. Prioritized Strategic Recommendations
        if report.recommendations:
            st.markdown("### Strategic Recommendations")
            for rec in report.recommendations:
                prio = rec.priority.value.lower()
                st.markdown(
                    f"""
                    <div class="rec-card rec-{prio}">
                        <span class="badge">{prio.upper()} PRIORITY</span>
                        <strong>{rec.title}</strong><br/>
                        <div style="margin-top:6px;">{rec.action}</div>
                        <div style="margin-top:6px; font-size:0.85rem; color:#334155;">
                            <strong>Evidence:</strong> {rec.rationale}<br/>
                            <strong>Expected Impact:</strong> {rec.expected_impact}
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

        if getattr(report, "follow_up_questions", None):
            st.markdown("###  Recommended Drill-Down Questions")
            fq_cols = st.columns(len(report.follow_up_questions))
            for idx, (col, fq) in enumerate(zip(fq_cols, report.follow_up_questions)):
                if col.button(f"↪ {fq}", key=f"fq_{idx}", width="stretch"):
                    st.session_state.auto_run_question = fq
                    st.rerun()

        # 7. Deduplicated Caveats & Dual Report Downloads (.html with live charts + .md)
        dedup_notes = list(dict.fromkeys(report.supporting_evidence_notes + analysis.data_caveats))
        if dedup_notes:
            with st.expander(" Methodology & Data Caveats", expanded=not report.is_successful):
                for note in dedup_notes:
                    st.markdown(f"- {note}")

        dl_col1, dl_col2, _ = st.columns([1.5, 1.5, 3])
        if getattr(report, "report_html", ""):
            dl_col1.download_button(
                label=" Download Full Interactive Report (.html)",
                data=report.report_html,
                file_name=f"{selected_db}_executive_report.html",
                mime="text/html",
                width="stretch",
            )
        if report.report_markdown:
            dl_col2.download_button(
                label=" Download Markdown Brief (.md)",
                data=report.report_markdown,
                file_name=f"{selected_db}_executive_brief.md",
                mime="text/markdown",
                width="stretch",
            )

# === TAB 2: SQL QUERIES & DATA AUDIT ===
with tab_sql:
    if not state or "sql_output" not in state:
        st.info("Executed SQL queries, self-correction attempt counts, and raw result tables will appear here.")
    else:
        sql_out = state["sql_output"]
        queries_by_id = {q.task_id: q for q in sql_out.generation.queries}

        if not sql_out.executions:
            st.warning("No SQL queries were executed for this request.")
            for err in sql_out.generation.generation_errors:
                st.error(err)
        else:
            for idx, ex in enumerate(sql_out.executions, 1):
                q_meta = queries_by_id.get(ex.task_id)
                header = f"Query {idx}: `{ex.task_id}` — {' Success' if ex.success else '❌ Failed'} ({ex.row_count} rows, {ex.attempts} attempt(s))"
                with st.expander(header, expanded=True):
                    if q_meta:
                        st.caption(f"**Purpose:** {q_meta.explanation} | **Tables:** {', '.join(q_meta.tables_used)}")
                    st.code(ex.query, language="sql")

                    if ex.error:
                        st.error(f"Execution Error: {ex.error}")
                    elif ex.rows:
                        df_res = pd.DataFrame(ex.rows)
                        st.dataframe(df_res, width="stretch")
                        st.download_button(
                            label=f"⬇ Download {ex.task_id} Results (.csv)",
                            data=df_res.to_csv(index=False),
                            file_name=f"{ex.task_id}.csv",
                            mime="text/csv",
                            key=f"dl_{ex.task_id}_{idx}",
                        )
            if st.session_state.audit_log:
                st.divider()
                st.markdown("####  Session Security & Query Audit Log")
                st.dataframe(pd.DataFrame(reversed(st.session_state.audit_log)), hide_index=True, width="stretch")

# === TAB 3: AGENT PIPELINE & REASONING ===
with tab_pipeline:
    if not state:
        st.info("Run a query to inspect the structured JSON outputs of all 5 agents.")
    else:
        if state.get("trace_log"):
            st.markdown("#### Execution Timeline")
            st.dataframe(pd.DataFrame(state["trace_log"]), hide_index=True, width="stretch")

        col_a, col_b = st.columns(2)
        with col_a:
            if "intent" in state:
                with st.expander("1️ Agent 1: BusinessIntent", expanded=True):
                    st.json(state["intent"].model_dump(mode="json"))
            if "analysis" in state:
                with st.expander("4️ Agent 4: Deterministic Analytics & Findings", expanded=True):
                    st.json(state["analysis"].model_dump(mode="json"))

        with col_b:
            if "plan" in state:
                with st.expander("2️ Agent 2: AnalysisPlan (DAG)", expanded=True):
                    st.json(state["plan"].model_dump(mode="json"))
            if "report" in state:
                with st.expander("5️ Agent 5: Report Metadata", expanded=False):
                    st.json(
                        state["report"].model_dump(
                            mode="json", exclude={"report_markdown", "report_html", "charts"}
                        )
                    )

# === TAB 4: LIVE DATABASE EXPLORER ===
with tab_db:
    st.markdown(f"#### {selected_db.title()} SQLite Schema & Live Table Preview")
    selected_table = st.selectbox("Select a table to inspect:", db_stats["tables"], index=0,key=f"db_explorer_table_{selected_db}_{active_policy.policy_id}")

    t_info = db_stats["schema"][selected_table]
    m1, m2, m3 = st.columns(3)
    m1.metric("Table", selected_table)
    m2.metric("Row Count", f"{db_stats['table_counts'][selected_table]:,}")
    m3.metric("Primary Key(s)", ", ".join(t_info["primary_keys"]) or "None")

    c_schema, c_preview = st.columns([1, 2])
    with c_schema:
        st.markdown("**Columns & Constraints**")
        fk_map = {}
        for fk in t_info["foreign_keys"]:
            for src_c, ref_c in zip(fk["columns"], fk["referenced_columns"]):
                fk_map[src_c] = f"→ {fk['referenced_table']}.{ref_c}"

        cols_display = [
            {
                "Column": c["name"],
                "Type": c["type"],
                "PK": "PK" if c["name"] in t_info["primary_keys"] else "",
                "Foreign Key": fk_map.get(c["name"], ""),
            }
            for c in t_info["columns"]
        ]
        st.dataframe(pd.DataFrame(cols_display), hide_index=True, width="stretch")

    with c_preview:
        st.markdown(f"**Sample Records (`{selected_table}`)**")
        preview_df = load_table_preview(selected_db, selected_table, limit=25)
        st.dataframe(preview_df, hide_index=True, width="stretch")