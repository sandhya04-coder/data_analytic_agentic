
from langchain_core.messages import SystemMessage, HumanMessage
from prompts.intent_agent_prompt import INTENT_AGENT_SYSTEM_PROMPT
from schemas.intent_schema import BusinessIntent
from config.llm_config import generate_structured


class IntentUnderstandingAgent:
    """
    Agent 1: Converts natural-language business questions
    into structured analytical requirements.
    """

    def understand(self, question: str, prior_context: str = "") -> BusinessIntent:
        """
        Understand a business question and return
        a validated BusinessIntent object.
        """

        if not isinstance(question, str) or not question.strip():
            raise ValueError(
                "Please provide a valid business question."
            )

        clean_question = question.strip()
        prompt_text = clean_question
        if prior_context and prior_context.strip():
            prompt_text = (
                f"CONVERSATION CONTEXT (from the immediately preceding turn):\n"
                f"{prior_context.strip()}\n\n"
                f"CURRENT FOLLOW-UP QUESTION:\n"
                f"{clean_question}\n\n"
                f"Resolve any references (e.g., 'that category', 'those states', 'break that down') "
                f"using the conversation context above so the resulting BusinessIntent is completely self-contained."
            )

        try:
            intent = generate_structured(
                BusinessIntent,
                [("user", prompt_text)],
                system_prompt=INTENT_AGENT_SYSTEM_PROMPT,
            )

            if not isinstance(intent, BusinessIntent):
                raise TypeError(
                    "LLM did not return a valid BusinessIntent object."
                )

            # Preserve the exact question submitted by the user.
            intent.original_question = clean_question

            return intent

        except Exception as error:
            raise RuntimeError(
                f"Intent understanding failed: {error}"
            ) from error
