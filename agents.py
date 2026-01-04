from rag import search
from llm import generate
from config import REQUIRE_LECTURER_REVIEW

# ⛑️ Intent detection must NEVER crash chat
try:
    from intent import detect_intent
except Exception:
    def detect_intent(text: str):
        return "default"


# =========================================================
# SYSTEM PROMPT (CORE)
# =========================================================
SYSTEM_CORE = (
    "You are an intelligent, conversational AI instructional assistant for "
    "pre-service teachers in Ghanaian Colleges of Education.\n\n"
    "INTERACTION RULES:\n"
    "- Respond naturally like a human tutor\n"
    "- Adapt depth and length based on user input\n"
    "- For short or vague inputs, ask a clarifying question first\n"
    "- Do NOT lecture unless necessary\n\n"
    "TEACHING STYLE:\n"
    "- Start simple, then deepen progressively\n"
    "- Pause to check understanding\n"
    "- Be interactive, not monologic\n\n"
    "ACADEMIC MODE:\n"
    "- Use headings only when helpful\n"
    "- Align with curriculum\n"
    "- Cite RAG sources only if used\n"
)


# =========================================================
# RAG CONTEXT FORMATTER (🔥 SAFE LIMIT)
# =========================================================
def _format_context(hits, max_chars: int = 2000):
    """
    Format RAG hits safely.
    HARD LIMIT to prevent GGUF context overflow.
    """
    if not hits:
        return "No retrieved context."

    lines = []
    total = 0

    for i, h in enumerate(hits, 1):
        block = (
            f"[{i}] Source: {h['source']} (score={h['score']:.3f})\n"
            f"{h['text']}\n"
        )

        total += len(block)
        if total > max_chars:
            break

        lines.append(block)

    return "\n".join(lines)


# =========================================================
# ROLE-AWARE CHAT (SAFE + FINAL)
# =========================================================
def tutor_chat_with_role(user_message: str, role: str):
    """
    Single, safe entry point for ALL chat requests.
    Used by /api/chat.
    """

    # 🔹 SAFE intent detection
    try:
        intent = detect_intent(user_message)
    except Exception:
        intent = "default"

    # 🔹 Greetings NEVER hit GGUF (fast + safe)
    if intent == "greeting":
        return "Hello 👋 How can I help you today?"

    # 🔹 Short chat = VERY light GGUF call
    if intent == "short_chat":
        return generate(
            "You are a friendly assistant. Respond briefly and naturally.",
            user_message,
            max_tokens=100
        )

    # =====================================================
    # ROLE-AWARE SYSTEM PROMPT
    # =====================================================
    if role == "admin":
        system_prompt = (
            SYSTEM_CORE +
            "\n\nYou are responding to an ADMIN overseeing AI-supported instruction. "
            "Emphasize governance, policy alignment, and system-level implications."
        )
    elif role == "lecturer":
        system_prompt = (
            SYSTEM_CORE +
            "\n\nYou are responding to a LECTURER. "
            "Emphasize pedagogy, assessment quality, and instructional strategies."
        )
    else:
        system_prompt = (
            SYSTEM_CORE +
            "\n\nYou are responding to a STUDENT (pre-service teacher). "
            "Use supportive tone, examples, and scaffolding."
        )

    # =====================================================
    # RAG + LLM (🔥 SAFE LIMITS)
    # =====================================================
    hits = search(user_message)
    ctx = _format_context(hits, max_chars=2000)

    user_prompt = (
        f"Context:\n{ctx}\n\n"
        f"User:\n{user_message}\n\n"
        "Guidelines:\n"
        "- Respond interactively\n"
        "- Ask a clarifying question if the input is vague\n"
        "- Only go deep if the user signals readiness"
    )

    return generate(
        system_prompt,
        user_prompt,
        max_tokens=256  # 🔥 CRITICAL: prevents GGUF 500 errors
    )


# =========================================================
# LESSON PLAN GENERATOR (SAFE)
# =========================================================
def generate_lesson_plan(topic: str, level: str, subject: str, duration_min: int):
    hits = search(f"{subject} {topic} curriculum objectives lesson plan")
    ctx = _format_context(hits, max_chars=2000)

    user_prompt = f"""RAG CONTEXT:
{ctx}

TASK:
Create a lesson plan for:
- Subject: {subject}
- Topic: {topic}
- Level: {level}
- Duration: {duration_min} minutes

Include:
1) Learning outcomes
2) Prior knowledge
3) Materials / ICT tools (low-bandwidth alternatives too)
4) Step-by-step teacher activities + learner activities
5) Differentiation aligned to Felder–Silverman
6) Formative assessment with a short rubric
7) Reflection prompts for the pre-service teacher
"""

    plan = generate(
        SYSTEM_CORE,
        user_prompt,
        max_tokens=512
    )

    if REQUIRE_LECTURER_REVIEW:
        plan += (
            "\n\nLECTURER REVIEW CHECKLIST:\n"
            "- Verify curriculum alignment\n"
            "- Check cultural relevance\n"
            "- Confirm assessment fairness\n"
            "- Confirm ICT feasibility\n"
        )

    return plan


# =========================================================
# RUBRIC FEEDBACK GENERATOR (SAFE)
# =========================================================
def rubric_feedback(lesson_text: str, rubric_text: str):
    hits = search("practicum supervision rubric lesson plan evaluation")
    ctx = _format_context(hits, max_chars=2000)

    user_prompt = f"""RAG CONTEXT:
{ctx}

TASK:
Evaluate the lesson plan using the rubric and return:
- Strengths
- Weaknesses
- Score breakdown (table)
- Improvement actions
- Short feedback email draft

RUBRIC:
{rubric_text}

LESSON PLAN:
{lesson_text}
"""

    fb = generate(
        SYSTEM_CORE,
        user_prompt,
        max_tokens=384
    )

    if REQUIRE_LECTURER_REVIEW:
        fb += "\n\nNOTE: Lecturer must validate this feedback before final submission."

    return fb
