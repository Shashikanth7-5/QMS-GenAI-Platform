"""Upload storage abstraction.

Production cloud apps should mount persistent storage or set
``UPLOAD_STORAGE_DIR`` to a managed volume path. The response keeps a
storage key instead of exposing local absolute paths to callers.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from werkzeug.utils import secure_filename

from config import UPLOAD_STORAGE_BACKEND, UPLOAD_STORAGE_DIR


class StorageError(RuntimeError):
    pass


def storage_status() -> dict:
    root = Path(UPLOAD_STORAGE_DIR)
    return {
        "backend": UPLOAD_STORAGE_BACKEND,
        "root": str(root),
        "exists": root.exists(),
        "writable": os.access(root, os.W_OK) if root.exists() else os.access(root.parent, os.W_OK),
    }


def save_upload(file, *, namespace: str, uploaded_by: str = "") -> dict:
    if UPLOAD_STORAGE_BACKEND != "local":
        raise StorageError(
            f"Unsupported UPLOAD_STORAGE_BACKEND={UPLOAD_STORAGE_BACKEND}. "
            "Use local with a mounted cloud volume, or add a provider adapter."
        )
    if not file or not file.filename:
        raise StorageError("Empty file")

    original_name = secure_filename(file.filename)
    today = datetime.utcnow().strftime("%Y%m%d")
    rel_dir = Path(namespace) / today
    target_dir = Path(UPLOAD_STORAGE_DIR) / rel_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    stored_name = f"{uuid4().hex}_{original_name}"
    stored_path = target_dir / stored_name
    file.save(stored_path)
    size = stored_path.stat().st_size
    storage_key = str(rel_dir / stored_name).replace("\\", "/")
    return {
        "id": stored_name,
        "name": original_name,
        "size": size,
        "type": file.mimetype or "Unknown",
        "storageBackend": UPLOAD_STORAGE_BACKEND,
        "storageKey": storage_key,
        "storedPath": str(stored_path),
        "uploadedAt": datetime.utcnow().isoformat() + "Z",
        "uploadedBy": uploaded_by,
    }
