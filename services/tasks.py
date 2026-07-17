# services/tasks.py
# ─────────────────────────────────────────────────────────
# CELERY TASKS — async CAPA generation
# Reuses the existing generate → save → embed pipeline.
# ─────────────────────────────────────────────────────────

from services.celery_app import celery_app


@celery_app.task(name="qms.generate_capa_async", bind=True)
def generate_capa_async(self, record_id: str) -> dict:
    """
    Async: generate a CAPA for one record, save it, embed it for RAG.
    Returns a small status dict. Never raises out of the task —
    failures are captured in the return payload.
    """
    try:
        from data.records import get_record_by_id, save_capa
        from services.ai_service import generate_capa

        record = get_record_by_id(record_id)
        if not record:
            return {"record_id": record_id, "status": "error",
                    "error": "record not found"}

        capa = generate_capa(record)
        capa["sourceRecordId"] = record_id
        saved = save_capa(capa)
        capa_id = saved.get("capaId") if isinstance(saved, dict) else capa.get("capaId")

        # Embed into vector store (non-blocking, best effort)
        try:
            from services.vector_store import embed_capa
            embed_capa(capa)
        except Exception as _e:
            print(f"[tasks] embed skipped: {_e}")

        return {"record_id": record_id, "status": "done", "capaId": capa_id}
    except Exception as e:
        return {"record_id": record_id, "status": "error", "error": str(e)}