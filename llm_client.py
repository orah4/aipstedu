import os
import requests

API_KEY = os.getenv("LOCAL_LLM_API_KEY")
BASE_URL = os.getenv("LOCAL_LLM_BASE_URL", "http://127.0.0.1:8001")

if not API_KEY:
    raise RuntimeError("LOCAL_LLM_API_KEY not set")

def chat(messages, max_tokens=512, temperature=0.7):
    r = requests.post(
        f"{BASE_URL}/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": "gguf-local",
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        },
        timeout=120,
    )

    r.raise_for_status()
    data = r.json()
    return data["choices"][0]["message"]["content"]
