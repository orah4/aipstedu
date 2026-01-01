import re

GREETING_PATTERNS = [
    r"^hi$",
    r"^hello$",
    r"^hey$",
    r"^good\s+(morning|afternoon|evening)$",
]

def detect_intent(text: str) -> str:
    t = text.lower().strip()

    # Greeting
    for p in GREETING_PATTERNS:
        if re.match(p, t):
            return "greeting"

    # Very short → conversational
    if len(t.split()) <= 3:
        return "short_chat"

    # Default
    return "academic"
