from rag import search
from llm import generate
from config import REQUIRE_LECTURER_REVIEW
from intent import detect_intent   # ✅ NEW IMPORT

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
    "ACADEMIC MODE (ONLY WHEN REQUESTED):\n"
    "- Use headings only when helpful\n"
    "- Align with curriculum\n"
    "- Cite RAG sources only if used\n"
)


# =========================================================
# RAG CONTEXT FORMATTER
# =========================================================
def _format_context(hits):
    if not hits:
        return "No retrieved context."
    lines = []
    for i, h in enumerate(hits, 1):
        lines.append(
            f"[{i}] Source: {h['source']} (score={h['score']:.3f})\n{h['text']}"
        )
    return "\n".join(lines)


# =========================================================
# MAIN CHAT ENTRY (INTENT-AWARE)
# =========================================================
def tutor_chat(user_message: str):
    intent = detect_intent(user_message)

    if intent == "greeting":
        return "Hello 👋 How can I help you today?"

    if intent == "short_chat":
        return generate(
            "You are a friendly assistant. Respond briefly and naturally.",
            user_message,
            max_tokens=100
        )

    # 🔥 Let the LLM decide interaction depth
    hits = search(user_message)
    ctx = _format_context(hits)

    user_prompt = (
    f"Context:\n{ctx}\n\n"
    f"User:\n{user_message}\n\n"
    "Guidelines:\n"
    "- Respond interactively\n"
    "- Ask a clarifying question if the input is vague\n"
    "- Only go deep if the user signals readiness"
)

    return generate(SYSTEM_CORE, user_prompt)

# =========================================================
# LESSON PLAN GENERATOR
# =========================================================
def generate_lesson_plan(topic: str, level: str, subject: str, duration_min: int):
    hits = search(f"{subject} {topic} curriculum objectives lesson plan")
    ctx = _format_context(hits)

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
3) Materials/ICT tools (low-bandwidth alternatives too)
4) Step-by-step teacher activities + learner activities
5) Differentiation aligned to Felder–Silverman
   (visual/verbal, active/reflective, sensing/intuitive, sequential/global)
6) Formative assessment with a short rubric
7) Reflection prompts for the pre-service teacher

If REQUIRE_LECTURER_REVIEW is enabled, add a final "LECTURER REVIEW CHECKLIST".
"""
    plan = generate(SYSTEM_CORE, user_prompt)

    if REQUIRE_LECTURER_REVIEW:
        plan += (
            "\n\nLECTURER REVIEW CHECKLIST:\n"
            "- Verify curriculum alignment\n"
            "- Check cultural relevance/examples\n"
            "- Confirm assessment fairness\n"
            "- Confirm ICT feasibility (offline/low bandwidth)\n"
        )

    return plan


# =========================================================
# RUBRIC FEEDBACK GENERATOR
# =========================================================
def rubric_feedback(lesson_text: str, rubric_text: str):
    hits = search("practicum supervision rubric lesson plan evaluation")
    ctx = _format_context(hits)

    user_prompt = f"""RAG CONTEXT:
{ctx}

TASK:
You are a practicum supervisor assistant.
Evaluate the lesson plan using the rubric and return:
- Strengths
- Weaknesses
- Score breakdown (table)
- Improvement actions (very concrete)
- A short feedback email draft to the student teacher

RUBRIC:
{rubric_text}

LESSON PLAN:
{lesson_text}
"""
    fb = generate(SYSTEM_CORE, user_prompt)

    if REQUIRE_LECTURER_REVIEW:
        fb += "\n\nNOTE: Lecturer must validate this feedback before final submission."

    return fb


# =========================================================
# ROLE-AWARE EXTENSION (NON-INVASIVE)
# =========================================================
def tutor_chat_with_role(user_message: str, role: str):
    """
    Role-aware wrapper with SAFE intent handling.
    """

    intent = detect_intent(user_message)

    # 🔹 Greetings & short chat must stay CLEAN
    if intent in ("greeting", "short_chat"):
        return tutor_chat(user_message)

    # 🔹 Role-specific framing ONLY for academic content
    if role == "admin":
        role_prefix = (
            "You are responding to an ADMIN overseeing AI-supported instruction. "
            "Emphasize governance, policy alignment, and system-level implications.\n\n"
        )
    elif role == "lecturer":
        role_prefix = (
            "You are responding to a LECTURER. "
            "Emphasize pedagogy, assessment quality, and instructional strategies.\n\n"
        )
    else:
        role_prefix = (
            "You are responding to a STUDENT (pre-service teacher). "
            "Use supportive tone, examples, and scaffolding.\n\n"
        )

    # ✅ Academic only
    return tutor_chat(role_prefix + user_message)
