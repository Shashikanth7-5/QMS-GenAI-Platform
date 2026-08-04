# services/vector_store.py
# ─────────────────────────────────────────────────────────
# VECTOR STORE — Sprint 3 RAG
# ChromaDB with built-in ONNX embeddings (all-MiniLM-L6-v2, 384-dim)
# Runs fully offline — no Hugging Face / external calls.
# Embeds saved CAPAs; retrieves top-k similar at generation time.
# ─────────────────────────────────────────────────────────

import os

import chromadb
from chromadb.config import Settings

from services.logging_config import get_logger

log = get_logger(__name__)

# Persist the vector DB to disk so embeddings survive restarts
_PERSIST_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "chroma_db")
_COLLECTION_NAME = "capa_history"

_client = None
_collection = None


def _get_collection():
    """Lazy-init the ChromaDB client + collection (singleton)."""
    global _client, _collection
    if _collection is not None:
        return _collection

    os.makedirs(_PERSIST_DIR, exist_ok=True)
    _client = chromadb.PersistentClient(
        path=_PERSIST_DIR,
        settings=Settings(anonymized_telemetry=False, allow_reset=True),
    )
    # Default embedding function = bundled ONNX all-MiniLM-L6-v2 (384-dim)
    _collection = _client.get_or_create_collection(
        name=_COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},   # cosine similarity
    )
    log.info("vector.collection_ready", extra={"count": _collection.count()})
    return _collection


def _enrich_from_record(capa: dict) -> dict:
    """
    DB CAPAs only store sourceRecordId — the title/type/sector live on the
    source record. Look it up so we embed the distinguishing text.
    Returns a dict with title/type/sector filled in (best effort).
    """
    info = {
        "title":  capa.get("sourceRecordTitle", "") or "",
        "type":   capa.get("sourceRecordType", "") or "",
        "sector": capa.get("sector", "") or "",
    }
    # If already present (older JSON CAPAs), use them as-is
    if info["title"] and info["type"]:
        return info
    # Otherwise look up the source record for its title/type/sector
    try:
        from data.records import get_record_by_id
        rec = get_record_by_id(capa.get("sourceRecordId", ""))
        if rec:
            info["title"]  = info["title"]  or rec.get("title", "")  or ""
            info["type"]   = info["type"]   or rec.get("type", "")   or ""
            info["sector"] = info["sector"] or rec.get("sector", "") or ""
    except Exception:
        log.warning("vector.record_lookup_failed", exc_info=True)
    return info


def _capa_to_text(capa: dict) -> str:
    """Build the text we embed — the fields that define similarity."""
    info = _enrich_from_record(capa)
    parts = [
        info.get("type", ""),
        info.get("sector", ""),
        info.get("title", ""),
        capa.get("rootCause", ""),
        capa.get("correctiveAction", ""),
        capa.get("preventiveAction", ""),
    ]
    return " | ".join(p for p in parts if p and str(p).strip())


def embed_capa(capa: dict) -> bool:
    """
    Embed a single CAPA into the vector store.
    Called from api_save() after a CAPA is saved.
    Returns True on success, False on any failure (never raises).
    """
    try:
        col = _get_collection()
        capa_id = capa.get("capaId")
        if not capa_id:
            return False
        text = _capa_to_text(capa)
        if not text.strip():
            return False
        info = _enrich_from_record(capa)
        # upsert = insert or update if it already exists
        col.upsert(
            ids=[capa_id],
            documents=[text],
            metadatas=[{
                "capaId":     capa_id,
                "recordId":   capa.get("sourceRecordId", "") or "",
                "type":       info.get("type", ""),
                "sector":     info.get("sector", ""),
                "title":      info.get("title", ""),
                "rootCause":  (capa.get("rootCause", "") or "")[:500],
                "riskRating": capa.get("riskRating", "") or "",
            }],
        )
        log.info("vector.embedded", extra={"capa_id": capa_id})
        return True
    except Exception:
        log.exception("vector.embed_failed")
        return False


def find_similar(record: dict, top_k: int = 3) -> list:
    """
    Find the top-k most similar past CAPAs for a given record.
    Called from generate_capa() (to inject context) and the API endpoint.
    Returns a list of dicts: [{capaId, recordId, title, rootCause, similarity}].
    Never raises — returns [] on failure.
    """
    try:
        col = _get_collection()
        if col.count() == 0:
            return []
        query_text = " | ".join(p for p in [
            record.get("type", ""),
            record.get("sector", ""),
            record.get("title", ""),
            record.get("description", ""),
        ] if p and str(p).strip())
        if not query_text.strip():
            return []

        n = min(top_k, col.count())
        res = col.query(query_texts=[query_text], n_results=n)

        out = []
        ids       = res.get("ids", [[]])[0]
        metas     = res.get("metadatas", [[]])[0]
        distances = res.get("distances", [[]])[0]
        for i, cid in enumerate(ids):
            meta = metas[i] if i < len(metas) else {}
            dist = distances[i] if i < len(distances) else 1.0
            # cosine distance → similarity (0..1)
            similarity = round(max(0.0, 1.0 - dist), 3)
            out.append({
                "capaId":     meta.get("capaId", cid),
                "recordId":   meta.get("recordId", ""),
                "title":      meta.get("title", ""),
                "type":       meta.get("type", ""),
                "rootCause":  meta.get("rootCause", ""),
                "riskRating": meta.get("riskRating", ""),
                "similarity": similarity,
            })
        return out
    except Exception:
        log.exception("vector.find_similar_failed")
        return []


def backfill_from_db() -> int:
    """
    One-time: embed all existing CAPAs already in the database.
    Run once so RAG has history to retrieve from.
    Returns count embedded.
    """
    try:
        from data.records import get_all_capas
        capas = get_all_capas()
        n = 0
        for capa in capas:
            if embed_capa(capa):
                n += 1
        log.info("vector.backfill_done", extra={"embedded": n, "total": len(capas)})
        return n
    except Exception:
        log.exception("vector.backfill_failed")
        return 0


def reset_collection() -> bool:
    """Wipe and recreate the collection (used before a clean re-backfill)."""
    global _client, _collection
    try:
        _get_collection()
        _client.delete_collection(_COLLECTION_NAME)
        _collection = None
        _get_collection()
        log.info("vector.collection_reset")
        return True
    except Exception:
        log.exception("vector.reset_failed")
        return False


def collection_stats() -> dict:
    """Quick stats for the /api/rag/similar status and tests."""
    try:
        col = _get_collection()
        return {"embedded_capas": col.count(), "collection": _COLLECTION_NAME}
    except Exception as e:
        return {"embedded_capas": 0, "error": str(e)}