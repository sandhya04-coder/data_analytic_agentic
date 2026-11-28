import random
import time
from google import genai
from google.genai import errors, types
import httpx
from langchain.chat_models import init_chat_model
import inspect
from config.settings import GOOGLE_API_KEY, LLM_MODEL

FALLBACK_MODEL = "gemini-3.8-flash"
REQUEST_TIMEOUT_MS = 35_000  # 35 seconds hard ceiling per HTTP call



def _validate_api_key() -> None:
    if not GOOGLE_API_KEY:
        raise ValueError(
            "GOOGLE_API_KEY is missing. Please configure it in your .env file."
        )


def get_gemini_client() -> genai.Client:
    """Return a fresh Google GenAI SDK client with a strict HTTP timeout."""
    _validate_api_key()
    return genai.Client(
        api_key=GOOGLE_API_KEY,
        http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS),
    )


def get_model_name() -> str:
    """Return the configured Gemini model name."""
    return LLM_MODEL


def get_llm():
    """Return the LangChain Gemini model with timeout and retry limits."""
    _validate_api_key()
    return init_chat_model(
        model=LLM_MODEL,
        model_provider="google_genai",
        temperature=0,
        api_key=GOOGLE_API_KEY,
        timeout=35,
        max_retries=2,
    )


def call_with_retry(fn, max_attempts: int = 4, base_delay: float = 2.0):
    """
    Retry transient Gemini 429/500/502/503/504 errors and HTTP timeouts
    using exponential backoff with random jitter.
    Supports both 0-arg callables `fn()` and 1-arg callables `fn(attempt)`.
    """
    accepts_attempt = len(inspect.signature(fn).parameters) >= 1

    for attempt in range(1, max_attempts + 1):
        try:
            return fn(attempt) if accepts_attempt else fn()
        except errors.APIError as err:
            if err.code not in {429, 500, 502, 503, 504} or attempt == max_attempts:
                raise
            wait = base_delay * (2 ** (attempt - 1)) + random.uniform(0.3, 1.5)
            print(
                f"[Gemini {err.code}] Transient spike, retrying in {wait:.1f}s "
                f"(attempt {attempt}/{max_attempts})...",
                flush=True,
            )
            time.sleep(wait)
        except (httpx.TimeoutException, TimeoutError) as err:
            if attempt == max_attempts:
                raise
            wait = base_delay * (2 ** (attempt - 1)) + random.uniform(0.3, 1.5)
            print(
                f"[Gemini Timeout] Request exceeded {REQUEST_TIMEOUT_MS // 1000}s ({type(err).__name__}), "
                f"retrying in {wait:.1f}s (attempt {attempt}/{max_attempts})...",
                flush=True,
            )
            time.sleep(wait)


def generate_structured(schema, messages, system_prompt=None):
    """
    messages: list of (role, text) tuples, role is "user" or "model".
    Returns a validated instance of `schema`.
    """
    contents = [
        types.Content(role=role, parts=[types.Part(text=text)])
        for role, text in messages
    ]

    def _invoke(attempt: int):
        client = get_gemini_client()
        active_model = (
            FALLBACK_MODEL
            if attempt >= 3 and get_model_name() != FALLBACK_MODEL
            else get_model_name()
        )
        if attempt >= 3 and active_model == FALLBACK_MODEL:
            print(f"[Gemini Failover] Switching to '{FALLBACK_MODEL}' for attempt {attempt}...", flush=True)

        return client.models.generate_content(
            model=active_model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0,
                response_mime_type="application/json",
                response_schema=schema,
            ),
        )

    response = call_with_retry(_invoke)
    return schema.model_validate_json(response.text)