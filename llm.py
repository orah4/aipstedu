import requests
import time
import threading
from typing import List, Dict

from config import (
    MOCK_LLM,
    LOCAL_LLM_API_KEY,
    LOCAL_LLM_BASE_URL,
)

# =========================================================
# GLOBAL LLM LOCK (CRITICAL)
# Ensures only ONE GGUF request runs at a time
# =========================================================
LLM_LOCK = threading.Lock()

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
    Call local OpenAI-compatible GGUF server (SERIALIZED).
    """

    if not LOCAL_LLM_API_KEY or not LOCAL_LLM_BASE_URL:
        return "⚠️ AI service is not configured correctly."

    url = f"{LOCAL_LLM_BASE_URL.rstrip('/')}/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {LOCAL_LLM_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": "gguf-local",
        "messages": messages,
        "temperature": float(temperature),
        "max_tokens": min(int(max_tokens), 120),  # 🔒 HARD SAFE LIMIT
    }

    print("[LLM] Waiting for lock...")

    # 🔒 SERIALIZE REQUESTS
    with LLM_LOCK:
        print("[LLM] Lock acquired")
        print("[LLM] Sending request to:", url)
        print("[LLM] max_tokens =", payload["max_tokens"])

        start = time.time()

        try:
            resp = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=300,  # ⏱️ Render-safe (5 minutes)
            )
            resp.raise_for_status()

        except requests.exceptions.Timeout:
            print("[LLM ERROR] Timeout")
            return "⚠️ The AI is busy. Please wait a moment and try again."

        except requests.exceptions.RequestException as e:
            print("[LLM ERROR]", str(e))
            return "⚠️ The AI service is currently busy. Please try again shortly."

        elapsed = round(time.time() - start, 2)
        print("[LLM] Response received in", elapsed, "seconds")
        print("[LLM] Lock released")

    try:
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError):
        print("[LLM ERROR] Invalid response:", resp.text)
        return "⚠️ AI returned an invalid response."


# =========================================================
# PUBLIC GENERATION ENTRY POINT
# =========================================================
def generate(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.6,
    max_tokens: int = 120,  # 🔒 MATCH REAL LIMIT
) -> str:
    """
    Unified generation entry point for the app.
    """

    if MOCK_LLM:
        return (
            "[MOCK_LLM]\n"
            "This is a mock response.\n\n"
            f"System prompt:\n{system_prompt[:120]}...\n\n"
            f"User prompt:\n{user_prompt[:180]}...\n"
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
