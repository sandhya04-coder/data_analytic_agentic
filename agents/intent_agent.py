
from langchain_core.messages import SystemMessage, HumanMessage
from prompts.intent_agent_prompt import INTENT_AGENT_SYSTEM_PROMPT
from schemas.intent_schema import BusinessIntent
from config.llm_config import generate_structured


class IntentUnderstandingAgent:
    """
    Agent 1: Converts natural-language business questions
    into structured analytical requirements.
    """

    def understand(self, question: str) -> BusinessIntent:
        """
        Understand a business question and return
        a validated BusinessIntent object.
        """

        if not isinstance(question, str) or not question.strip():
            raise ValueError(
                "Please provide a valid business question."
            )

        messages = [
            SystemMessage(content=INTENT_AGENT_SYSTEM_PROMPT),
            HumanMessage(content=question.strip())
        ]

        try:
            
            intent = generate_structured(
                BusinessIntent,
                [("user", question.strip())],
                system_prompt=INTENT_AGENT_SYSTEM_PROMPT,
            )

            if not isinstance(intent, BusinessIntent):
                raise TypeError(
                    "LLM did not return a valid BusinessIntent object."
                )

            # Preserve the exact question submitted by the user.
            intent.original_question = question.strip()

            return intent

        except Exception as error:
            raise RuntimeError(
                f"Intent understanding failed: {error}"
            ) from error
