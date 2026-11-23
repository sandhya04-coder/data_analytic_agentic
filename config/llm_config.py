
from langchain.chat_models import init_chat_model
from google import genai

from config.settings import GOOGLE_API_KEY, LLM_MODEL

from google.genai import types
import time
from google import genai
from google.genai import errors, types
from config.settings import GOOGLE_API_KEY, LLM_MODEL


def call_with_retry(fn, max_attempts: int = 4, base_delay: float = 2.0):
    """Retry transient Gemini 429/503/504 errors with exponential backoff."""
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except errors.APIError as err:
            if err.code not in {429, 500, 502, 503, 504} or attempt == max_attempts:
                raise
            wait = base_delay * (2 ** (attempt - 1))
            print(f"[Gemini {err.code}] Transient spike, retrying in {wait:.1f}s (attempt {attempt}/{max_attempts})...")
            time.sleep(wait)
def generate_structured(schema, messages, system_prompt=None):
    """
    messages: list of (role, text) tuples, role is "user" or "model".
    Returns a validated instance of `schema`.
    """
    client = get_gemini_client()
    contents = [
        types.Content(role=role, parts=[types.Part(text=text)])
        for role, text in messages
    ]
    response = call_with_retry(
    lambda: client.models.generate_content(
        model=get_model_name(),
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0,
            response_mime_type="application/json",
            response_schema=schema,
        ),
    )
)
    return schema.model_validate_json(response.text)
def _validate_api_key():
    if not GOOGLE_API_KEY:
        raise ValueError(
            "GOOGLE_API_KEY is missing. "
            "Please configure it in your .env file."
        )


def get_llm():
    """Return the LangChain Gemini model."""
    _validate_api_key()

    return init_chat_model(
        model=LLM_MODEL,
        model_provider="google_genai",
        temperature=0,
        api_key=GOOGLE_API_KEY
    )


def get_gemini_client():
    """Return the official Google GenAI SDK client."""
    _validate_api_key()

    return genai.Client(
        api_key=GOOGLE_API_KEY
    )


def get_model_name():
    """Return the configured Gemini model name."""
    return LLM_MODEL
