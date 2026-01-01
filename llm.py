import requests
from typing import List, Dict

from config import (
    MOCK_LLM,
    LOCAL_LLM_API_KEY,
    LOCAL_LLM_BASE_URL,
)

# =========================================================
# DEBUG VISIBILITY
# =========================================================
print("[DEBUG] MOCK_LLM =", MOCK_LLM)
print("[DEBUG] LOCAL_LLM_BASE_URL =", LOCAL_LLM_BASE_URL)
print("[DEBUG] USING API KEY =", bool(LOCAL_LLM_API_KEY))


# =========================================================
# INTERNAL API CHAT CALL
# =========================================================
def _api_chat(
    messages: List[Dict[str, str]],
    temperature: float,
    max_tokens: int
) -> str:
    """
    Call local OpenAI-compatible GGUF server
    """

    if not LOCAL_LLM_API_KEY or not LOCAL_LLM_BASE_URL:
        raise RuntimeError(
            "LOCAL_LLM_API_KEY or LOCAL_LLM_BASE_URL not set in .env"
        )

    url = f"{LOCAL_LLM_BASE_URL.rstrip('/')}/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {LOCAL_LLM_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": "gguf-local",
        "messages": messages,
        "temperature": float(temperature),
        "max_tokens": int(max_tokens),
    }

    try:
        resp = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=600,   # 🔥 GGUF SAFE (10 minutes)
        )
        resp.raise_for_status()

    except requests.exceptions.Timeout:
        raise RuntimeError(
            "LLM request timed out. The model is still generating. "
            "Try reducing max_tokens or enabling streaming."
        )

    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"LLM API request failed: {e}")

    data = resp.json()

    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError):
        raise RuntimeError(f"Invalid LLM response format: {data}")


# =========================================================
# PUBLIC GENERATION ENTRY POINT
# =========================================================
def generate(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.6,
    max_tokens: int = 1024,   # ✅ SAFE DEFAULT (IMPORTANT)
) -> str:
    """
    Unified generation entry point for the app.
    This function is used everywhere (chat, lesson, feedback, etc.)
    """

    if MOCK_LLM:
        return (
            "[MOCK_LLM]\n"
            "I understood your request. Here is a structured, curriculum-aligned output.\n\n"
            f"System prompt summary:\n{system_prompt[:120]}...\n\n"
            f"User prompt summary:\n{user_prompt[:180]}...\n"
        )

    messages = [
        {"role": "system", "content": system_prompt.strip()},
        {"role": "user", "content": user_prompt.strip()},
    ]

    return _api_chat(
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
