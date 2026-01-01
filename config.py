import os
from dotenv import load_dotenv

# =========================================================
# FORCE .env LOADING (Windows + Flask reload safe)
# =========================================================
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(PROJECT_ROOT, ".env")

load_dotenv(dotenv_path=ENV_PATH, override=True)

# =========================================================
# BASE DIRECTORIES
# =========================================================
BASE_DIR = PROJECT_ROOT

DATA_DIR = os.path.join(BASE_DIR, "data")
KB_DIR = os.path.join(DATA_DIR, "knowledge_base")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")

STORAGE_DIR = os.path.join(BASE_DIR, "storage")
FAISS_INDEX_PATH = os.path.join(STORAGE_DIR, "faiss.index")
CHUNKS_PATH = os.path.join(STORAGE_DIR, "chunks.jsonl")
SQLITE_PATH = os.path.join(STORAGE_DIR, "app.sqlite3")

os.makedirs(KB_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(STORAGE_DIR, exist_ok=True)

# =========================================================
# LLM BACKEND SELECTION
# =========================================================
# Options:
#   "api"        → use OpenAI-compatible local server (RECOMMENDED)
#   "local_gguf" → embed GGUF directly (legacy)
#   "mock"       → mock responses
LLM_BACKEND = os.getenv("LLM_BACKEND", "api").strip().lower()

MOCK_LLM = LLM_BACKEND == "mock"

# =========================================================
# API-BASED LLM CONFIG (PRIMARY MODE)
# =========================================================
LOCAL_LLM_API_KEY = os.getenv("LOCAL_LLM_API_KEY", "").strip()
LOCAL_LLM_BASE_URL = os.getenv("LOCAL_LLM_BASE_URL", "").strip()

if LLM_BACKEND == "api":
    if not LOCAL_LLM_API_KEY or not LOCAL_LLM_BASE_URL:
        raise RuntimeError(
            "LLM_BACKEND=api but LOCAL_LLM_API_KEY or LOCAL_LLM_BASE_URL is missing"
        )

# =========================================================
# EMBEDDED GGUF CONFIG (LEGACY / OPTIONAL)
# =========================================================
GGUF_MODEL_PATH = os.getenv("GGUF_MODEL_PATH", "").strip()

if LLM_BACKEND == "local_gguf":
    if not GGUF_MODEL_PATH:
        raise RuntimeError(
            "LLM_BACKEND=local_gguf but GGUF_MODEL_PATH is empty"
        )
    if not os.path.isabs(GGUF_MODEL_PATH):
        raise RuntimeError(
            f"GGUF_MODEL_PATH must be an absolute path. Got: {GGUF_MODEL_PATH}"
        )
    if not os.path.exists(GGUF_MODEL_PATH):
        raise RuntimeError(
            f"GGUF model file not found at: {GGUF_MODEL_PATH}"
        )

# =========================================================
# EMBEDDINGS / RAG
# =========================================================
EMBED_MODEL_NAME = os.getenv(
    "EMBED_MODEL_NAME",
    "sentence-transformers/all-MiniLM-L6-v2"
)

TOP_K = int(os.getenv("TOP_K", "5"))

# =========================================================
# GOVERNANCE / HUMAN-IN-THE-LOOP
# =========================================================
REQUIRE_LECTURER_REVIEW = os.getenv(
    "REQUIRE_LECTURER_REVIEW", "1"
).strip() == "1"

# =========================================================
# DEBUG VISIBILITY
# =========================================================
print("========== CONFIG LOADED ==========")
print("LLM_BACKEND =", LLM_BACKEND)
print("MOCK_LLM =", MOCK_LLM)
print("LOCAL_LLM_BASE_URL =", LOCAL_LLM_BASE_URL if LLM_BACKEND == "api" else "N/A")
print("GGUF_MODEL_PATH =", GGUF_MODEL_PATH if LLM_BACKEND == "local_gguf" else "N/A")
print("TOP_K =", TOP_K)
print("REQUIRE_LECTURER_REVIEW =", REQUIRE_LECTURER_REVIEW)
print("===================================")
