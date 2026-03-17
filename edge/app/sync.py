import json
import logging
from pathlib import Path

from .models import StructuredData

logger = logging.getLogger(__name__)


def enqueue_pending(pending_dir: Path, payload: StructuredData) -> Path:
    pending_dir.mkdir(parents=True, exist_ok=True)
    file_name = f"pending-{payload.document_name.replace(' ', '_')}.json"
    path = pending_dir / file_name
    index = 1
    while path.exists():
        path = pending_dir / f"pending-{payload.document_name.replace(' ', '_')}-{index}.json"
        index += 1

    path.write_text(json.dumps(payload.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Payload enfileirado para sincronização: %s", path)
    return path


def sync_pending(pending_dir: Path) -> dict:
    from .pipeline import send_to_backend

    pending_dir.mkdir(parents=True, exist_ok=True)
    pending_files = sorted(pending_dir.glob("pending-*.json"))
    synced = 0
    failed = 0

    for file_path in pending_files:
        data = json.loads(file_path.read_text(encoding="utf-8"))
        payload = StructuredData(**data)
        try:
            send_to_backend(payload)
            file_path.unlink(missing_ok=True)
            synced += 1
        except Exception:
            failed += 1

    return {"total": len(pending_files), "synced": synced, "failed": failed}
