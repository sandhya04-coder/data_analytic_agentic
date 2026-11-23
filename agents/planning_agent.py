import json
from google.genai import types
from database.connection import get_table_names
from config.llm_config import get_gemini_client, get_model_name,call_with_retry

from prompts.planning_agent_prompt import (
    PLANNING_AGENT_SYSTEM_PROMPT
)

from schemas.intent_schema import BusinessIntent
from schemas.planning_schema import AnalysisPlan

from tools.database_tools import (
    get_database_overview,
    get_table_schema,
    get_table_relationships,
    profile_table
)


class PlanningAgent:
    """
    Agent 2: Converts BusinessIntent into an executable
    AnalysisPlan using Gemini-native function calling.

    Gemini autonomously decides which database tools
    to invoke and what arguments to provide.
    """

    def __init__(self, max_tool_calls: int = 12 , max_repairs: int = 2):

        self.client = get_gemini_client()
        self.model = get_model_name()

        self.max_tool_calls = max_tool_calls
        self.max_repairs = max_repairs
        self.tools = {
            "get_database_overview": get_database_overview,
            "get_table_schema": get_table_schema,
            "get_table_relationships": get_table_relationships,
            "profile_table": profile_table
        }

        self.function_tool = self._create_function_tool()

    def _create_function_tool(self):
        """
        Declare the available database functions
        using the official Google GenAI SDK.
        """

        declarations = [

            types.FunctionDeclaration(
                name="get_database_overview",
                description=(
                    "Discover all tables available in the database. "
                    "Use this to understand the database structure."
                ),
                parameters=types.Schema(
                    type="OBJECT",
                    properties={}
                )
            ),

            types.FunctionDeclaration(
                name="get_table_schema",
                description=(
                    "Retrieve columns, data types, primary keys "
                    "and foreign keys for a specified table."
                ),
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "table_name": types.Schema(
                            type="STRING",
                            description="Name of the database table."
                        )
                    },
                    required=["table_name"]
                )
            ),

            types.FunctionDeclaration(
                name="get_table_relationships",
                description=(
                    "Retrieve declared foreign-key relationships "
                    "between database tables."
                ),
                parameters=types.Schema(
                    type="OBJECT",
                    properties={}
                )
            ),

            types.FunctionDeclaration(
                name="profile_table",
                description=(
                    "Profile a database table. Returns row count, "
                    "columns, null counts, date ranges and sample records. "
                    "Use this to understand actual data availability."
                ),
                parameters=types.Schema(
                    type="OBJECT",
                    properties={
                        "table_name": types.Schema(
                            type="STRING",
                            description="Name of the table to profile."
                        ),
                        "sample_size": types.Schema(
                            type="INTEGER",
                            description=(
                                "Number of sample records to retrieve. "
                                "Must be between 1 and 20. Defaults to 5."
                            )
                        )
                    },
                    required=["table_name"]
                )
            )
        ]

        return types.Tool(
            function_declarations=declarations
        )

    def _execute_tool(self, function_call):
        """
        Execute a function selected by Gemini and
        return a JSON-compatible result.
        """

        tool_name = function_call.name
        tool_args = function_call.args or {}

        selected_tool = self.tools.get(tool_name)

        if selected_tool is None:
            return {
                "error": f"Unknown database tool: {tool_name}"
            }

        try:
            result = selected_tool.invoke(dict(tool_args))

            # Convert dates and other non-JSON values safely.
            return json.loads(
                json.dumps(result, default=str)
            )

        except Exception as error:
            return {
                "error": str(error)
            }

    def _parse_analysis_plan(self, response_text, intent):
        """
        Parse Gemini's final JSON response and validate
        it against the AnalysisPlan Pydantic model.
        """

        if not response_text:
            raise ValueError(
                "Gemini returned an empty planning response."
            )

        cleaned_text = response_text.strip()

        # Handle optional Markdown JSON code fences.
        if cleaned_text.startswith("```"):
            cleaned_text = cleaned_text.split("\n", 1)[-1]

            if cleaned_text.endswith("```"):
                cleaned_text = cleaned_text[:-3].strip()

        try:
            plan_data = json.loads(cleaned_text)

        except json.JSONDecodeError:
            # Attempt to extract a JSON object if
            # Gemini included surrounding text.
            start = cleaned_text.find("{")
            end = cleaned_text.rfind("}")

            if start == -1 or end == -1:
                raise ValueError(
                    "Gemini did not return valid JSON."
                )

            plan_data = json.loads(
                cleaned_text[start:end + 1]
            )

        analysis_plan = AnalysisPlan.model_validate(
            plan_data
        )

        analysis_plan.original_question = intent.original_question

        invalid_tables = set(analysis_plan.selected_tables) - set(get_table_names())
        if invalid_tables:
            raise ValueError(f"Plan uses tables that do not exist: {sorted(invalid_tables)}")

        return analysis_plan

    def plan(self, intent: BusinessIntent) -> AnalysisPlan:
        """
        Generate an AnalysisPlan through native
        Gemini function calling.
        """

        if not isinstance(intent, BusinessIntent):
            raise TypeError(
                "PlanningAgent requires a BusinessIntent object."
            )

        if intent.needs_clarification:
            raise ValueError(
                "Cannot create a plan until the user's "
                "clarification has been obtained."
            )

        user_message = f"""
Create an evidence-based AnalysisPlan for the following
BusinessIntent.

BUSINESS INTENT:

{intent.model_dump_json(indent=2)}

ANALYSIS PLAN JSON SCHEMA:

{json.dumps(AnalysisPlan.model_json_schema(), indent=2)}

Use the database discovery functions whenever necessary.

Important:
- Discover actual database tables and schemas.
- Profile relevant tables to inspect actual data.
- Check date ranges when the question contains a time requirement.
- Map metrics and dimensions to actual columns.
- Do not invent tables, columns or relationships.
- Do not generate SQL.
- Do not execute analytical queries.
- Do not silently replace unavailable date ranges.
- Identify all relevant data limitations.

When discovery is complete, return ONLY a JSON object
conforming to the AnalysisPlan schema.
"""

        contents = [
            types.Content(
                role="user",
                parts=[
                    types.Part(text=user_message)
                ]
            )
        ]

        config = types.GenerateContentConfig(
            system_instruction=PLANNING_AGENT_SYSTEM_PROMPT,
            temperature=0,
            tools=[self.function_tool],
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(
                    mode="AUTO"
                )
            )
        )

        tool_call_count = 0
        repair_attempts = 0

        while True:

            response = call_with_retry(
                lambda: self.client.models.generate_content(
                    model=self.model,
                    contents=contents,
                    config=config,
                )
            )

            if not response.candidates:
                raise RuntimeError(
                    "Gemini returned no response candidates."
                )

            candidate = response.candidates[0]
            model_content = candidate.content

            if model_content is None:
                raise RuntimeError(
                    "Gemini returned an empty candidate."
                )

            # Preserve the ORIGINAL Gemini Content object.
            # This retains function-call metadata and
            # thought signatures across tool-call rounds.
            contents.append(model_content)

            function_calls = [
                part.function_call
                for part in (model_content.parts or [])
                if part.function_call is not None
            ]

            # No function calls means Gemini has completed
            # its database discovery and produced its final answer.
            if not function_calls:
                try:
                    return self._parse_analysis_plan(response.text, intent)
                except Exception as error:
                    if repair_attempts >= self.max_repairs:
                        raise RuntimeError(
                            f"Planning Agent could not produce a valid AnalysisPlan: {error}"
                        ) from error
                    repair_attempts += 1
                    contents.append(types.Content(role="user", parts=[types.Part(text=(
                        f"Your previous response was invalid: {error}\n"
                        "Return ONLY a corrected JSON object conforming to the AnalysisPlan schema."
                    ))]))
                    continue

            if tool_call_count + len(function_calls) > self.max_tool_calls:
                contents.append(types.Content(role="user", parts=[
                    *[types.Part.from_function_response(
                        name=fc.name, response={"error": "Tool-call limit reached."})
                    for fc in function_calls],
                    types.Part(text="Tool limit reached. Return ONLY the final AnalysisPlan JSON now, "
                                    "using what you have already discovered.")
                ]))
                config = types.GenerateContentConfig(
                    system_instruction=PLANNING_AGENT_SYSTEM_PROMPT,
                    temperature=0,
                    tools=[self.function_tool],
                    tool_config=types.ToolConfig(
                        function_calling_config=types.FunctionCallingConfig(mode="NONE")
                    )
                )
                continue

            function_responses = []

            for function_call in function_calls:

                tool_result = self._execute_tool(
                    function_call
                )

                function_responses.append(
                    types.Part.from_function_response(
                        name=function_call.name,
                        response=tool_result
                    )
                )

                tool_call_count += 1

            # Send all tool results back to Gemini.
            contents.append(
                types.Content(
                    role="user",
                    parts=function_responses
                )
            )

    def close(self):
        """Close the underlying Google GenAI client."""
        self.client.close()