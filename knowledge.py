"""Per-bot knowledge base (RAG) — chunking + vector math. Stdlib only.

The design is deliberately the simplest thing that works:

  - Documents are split into fixed-size character windows with overlap.
  - Each chunk's embedding (from Ollama / OpenAI-compat via llm.embed) is
    L2-normalized and stored as a packed float32 BLOB in SQLite.
  - Retrieval is brute-force cosine similarity (= dot product, since vectors
    are pre-normalized) over ONE conversation's chunks. No index, no external
    vector database. Fast enough for thousands of chunks per bot.

If a bot's library ever grows past tens of thousands of chunks, the only thing
that needs to change is `retrieve()` — swap the Python loop for sqlite-vec.
Nothing else in the codebase knows how retrieval is implemented.
"""
import math
import struct

# Chunking defaults. ~1000 chars ≈ 200-300 tokens — comfortably inside any
# embedding model's context, with overlap so a fact split across a boundary
# still lands wholly inside at least one chunk.
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping character windows, preferring to break on
    whitespace so chunks don't slice through the middle of a word."""
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]

    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + size, n)
        # Prefer to end on a whitespace boundary within the last ~15% of the
        # window, so we don't cut a word in half. Fall back to a hard cut.
        if end < n:
            window_floor = start + int(size * 0.85)
            break_at = text.rfind(" ", window_floor, end)
            if break_at == -1:
                break_at = text.rfind("\n", window_floor, end)
            if break_at != -1 and break_at > start:
                end = break_at
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return chunks


def normalize(vec: list[float]) -> list[float]:
    """L2-normalize so cosine similarity reduces to a plain dot product."""
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        return list(vec)
    return [x / norm for x in vec]


def pack_vector(vec: list[float]) -> bytes:
    """Pack a float list into a compact float32 BLOB for SQLite storage."""
    return struct.pack(f"<{len(vec)}f", *vec)


def unpack_vector(blob: bytes) -> list[float]:
    """Inverse of pack_vector."""
    return list(struct.unpack(f"<{len(blob) // 4}f", blob))


def dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def top_k(query_vec: list[float], chunks: list[dict], k: int = 5) -> list[dict]:
    """Rank pre-stored chunks against a query vector by cosine similarity.

    `chunks` is a list of dicts each carrying at least `embedding` (already a
    list[float], L2-normalized at store time) plus whatever metadata the caller
    wants back (text, filename). Returns the top-k dicts with a `score` added,
    highest first. The query vector is normalized here so callers don't have to.
    """
    q = normalize(query_vec)
    scored = []
    for c in chunks:
        emb = c.get("embedding")
        if not emb:
            continue
        scored.append((dot(q, emb), c))
    scored.sort(key=lambda t: t[0], reverse=True)
    out = []
    for score, c in scored[:k]:
        item = {key: val for key, val in c.items() if key != "embedding"}
        item["score"] = score
        out.append(item)
    return out


def top_k_balanced(query_vec: list[float], chunks: list[dict], k: int = 5,
                   doc_key: str = "filename") -> list[dict]:
    """Like top_k, but no single source document may monopolize the results.

    Plain top-k over a bot with one huge (or noisy/OCR'd) book will fill every
    slot from that book and drown out smaller books — so a chunk that is rank #1
    *within its own book* never surfaces if it's rank #30 globally. This caps
    each document to ~ceil(k / num_docs) chunks (highest-scoring first), then
    fills any remaining slots with the next-best chunks regardless of source.
    Single-document bots behave exactly like top_k.
    """
    q = normalize(query_vec)
    scored = []
    for c in chunks:
        emb = c.get("embedding")
        if not emb:
            continue
        scored.append((dot(q, emb), c))
    if not scored:
        return []
    scored.sort(key=lambda t: t[0], reverse=True)

    ndocs = len({c.get(doc_key) for _, c in scored}) or 1
    per_doc_cap = max(1, -(-k // ndocs))  # ceil(k / ndocs)

    def _emit(score, c):
        item = {key: val for key, val in c.items() if key != "embedding"}
        item["score"] = score
        return item

    out, per_count, taken = [], {}, set()
    # Pass 1 — honor the per-document cap (global score order within each doc).
    for i, (score, c) in enumerate(scored):
        doc = c.get(doc_key)
        if per_count.get(doc, 0) >= per_doc_cap:
            continue
        per_count[doc] = per_count.get(doc, 0) + 1
        taken.add(i)
        out.append(_emit(score, c))
        if len(out) >= k:
            return out
    # Pass 2 — fewer docs than slots: fill the rest with next-best overall.
    for i, (score, c) in enumerate(scored):
        if i in taken:
            continue
        out.append(_emit(score, c))
        if len(out) >= k:
            break
    return out


def build_context_block(passages: list[dict]) -> str:
    """Format retrieved passages into a system-prompt augmentation block.

    Each passage dict carries `text` and `filename`. The block is prepended to
    the bot's system prompt so the model answers grounded in the library.
    """
    if not passages:
        return ""
    lines = [
        "## Knowledge base excerpts",
        "Use the following excerpts from the user's library to answer. If the",
        "answer isn't in them, say so rather than inventing facts.",
        "",
    ]
    for p in passages:
        src = p.get("filename") or "document"
        lines.append(f"[source: {src}]")
        lines.append((p.get("text") or "").strip())
        lines.append("")
    return "\n".join(lines).strip()
