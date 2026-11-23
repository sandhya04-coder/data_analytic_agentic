
from agents.intent_agent import IntentUnderstandingAgent
from schemas.intent_schema import AnalysisType


def main():

    agent = IntentUnderstandingAgent()

    questions = [
        # # "What is our total revenue?",

         "Show monthly revenue trends for 1997.",

        # # "Which five products generated the highest revenue?",

        # # "Compare sales across different countries.",

        # # "Why did our revenue decline in the last quarter?"
    ]

    for question in questions:

        print("\n" + "=" * 65)
        print(f"QUESTION: {question}")

        try:
            intent = agent.understand(question)

            print("\nSTRUCTURED INTENT:")
            print(intent.model_dump_json(indent=4))

            print("\nVALIDATION:")

            if "Why did our revenue decline" in question:
                assert intent.investigation_required
                assert AnalysisType.ROOT_CAUSE in intent.analysis_types

            print("PASSED")

        except Exception as error:
            print(f"FAILED: {error}")


if __name__ == "__main__":
    main()
