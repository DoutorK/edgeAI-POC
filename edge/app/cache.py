import hashlib
import json
from pathlib import Path
from typing import Optional


def _safe_name(base_text: str) -> str:
    return hashlib.sha256(base_text.encode("utf-8")).hexdigest()


def get_cache_path(cache_dir: Path, base_text: str) -> Path:
    return cache_dir / f"{_safe_name(base_text)}.json"


def save_cache(cache_dir: Path, base_text: str, payload: dict) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = get_cache_path(cache_dir, base_text)
    cache_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return cache_file


def load_cache(cache_dir: Path, base_text: str) -> Optional[dict]:
    cache_file = get_cache_path(cache_dir, base_text)
    if not cache_file.exists():
        return None
    return json.loads(cache_file.read_text(encoding="utf-8"))
