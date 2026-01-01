import os
import json
import numpy as np
import faiss

from sentence_transformers import SentenceTransformer
from config import (
    EMBED_MODEL_NAME,
    TOP_K,
    FAISS_INDEX_PATH,
    CHUNKS_PATH,
    STORAGE_DIR
)

# =========================================================
# GLOBALS (lazy-loaded)
# =========================================================
_embedder = None


# =========================================================
# EMBEDDING MODEL LOADER (LAZY + SAFE)
# =========================================================
def _get_embedder():
    global _embedder
    if _embedder is None:
        _embedder = SentenceTransformer(
            EMBED_MODEL_NAME,
            device="cpu"   # force CPU (important for stability)
        )
    return _embedder


# =========================================================
# VECTOR NORMALISATION
# =========================================================
def _normalize(v: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(v, axis=1, keepdims=True) + 1e-12
    return v / norm


# =========================================================
# STORAGE HELPERS
# =========================================================
def load_chunks():
    if not os.path.exists(CHUNKS_PATH):
        return []

    chunks = []
    with open(CHUNKS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            chunks.append(json.loads(line))
    return chunks


def save_chunks(chunks):
    os.makedirs(STORAGE_DIR, exist_ok=True)

    with open(CHUNKS_PATH, "w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")


# =========================================================
# SAFE TEXT CHUNKING (CRITICAL FIX)
# =========================================================
def chunk_text(
    text: str,
    source: str,
    chunk_size: int = 800,
    max_chunks: int = 200
):
    """
    Safely chunk text for RAG ingestion.

    - Prevents runaway memory usage
    - No overlap (overlap caused MemoryError before)
    - Enforces hard size limits
    """

    text = text.strip()
    if not text:
        return []

    # HARD SAFETY LIMIT (VERY IMPORTANT)
    MAX_TEXT_LENGTH = 200_000  # ~200 KB text max

    if len(text) > MAX_TEXT_LENGTH:
        raise ValueError(
            f"Text too large ({len(text)} chars). "
            f"Maximum allowed is {MAX_TEXT_LENGTH} characters. "
            f"Please ingest smaller sections."
        )

    chunks = []
    start = 0
    text_len = len(text)

    while start < text_len and len(chunks) < max_chunks:
        end = min(text_len, start + chunk_size)
        chunk = text[start:end]

        chunks.append({
            "source": source,
            "text": chunk
        })

        start = end  # ❗ NO OVERLAP (KEY FIX)

    return chunks


# =========================================================
# FAISS INDEX BUILDING (MEMORY-SAFE)
# =========================================================
def build_index(chunks):
    """
    Builds cosine-similarity FAISS index using normalized embeddings.
    """

    if not chunks:
        return

    os.makedirs(STORAGE_DIR, exist_ok=True)

    embedder = _get_embedder()
    texts = [c["text"] for c in chunks]

    # Encode in small batches to avoid RAM spikes
    BATCH_SIZE = 32
    embeddings = []

    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i:i + BATCH_SIZE]
        embs = embedder.encode(
            batch,
            convert_to_numpy=True,
            show_progress_bar=False
        )
        embeddings.append(embs)

    embs = np.vstack(embeddings).astype("float32")
    embs = _normalize(embs)

    dim = embs.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(embs)

    faiss.write_index(index, FAISS_INDEX_PATH)


# =========================================================
# INGESTION PIPELINE (SAFE + GUARDED)
# =========================================================
def ingest_text(text: str, source: str):
    chunks = load_chunks()

    try:
        new_chunks = chunk_text(text, source=source)
    except ValueError as e:
        raise RuntimeError(str(e))

    chunks.extend(new_chunks)

    save_chunks(chunks)
    build_index(chunks)

    return len(new_chunks)


# =========================================================
# SEARCH (RAG RETRIEVAL)
# =========================================================
def search(query: str, top_k: int = TOP_K):
    chunks = load_chunks()

    if not chunks or not os.path.exists(FAISS_INDEX_PATH):
        return []

    index = faiss.read_index(FAISS_INDEX_PATH)

    embedder = _get_embedder()
    q = embedder.encode(
        [query],
        convert_to_numpy=True,
        show_progress_bar=False
    ).astype("float32")

    q = _normalize(q)

    scores, idxs = index.search(q, top_k)

    results = []
    for score, idx in zip(scores[0], idxs[0]):
        if idx < 0 or idx >= len(chunks):
            continue

        c = chunks[idx]
        results.append({
            "score": float(score),
            "source": c.get("source", ""),
            "text": c.get("text", "")
        })

    return results
