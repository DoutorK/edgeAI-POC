import json
import logging
from pathlib import Path

import requests

from .config import settings
from .cache import load_cache, save_cache
from .classifier import classify_document
from .extractors import extract_dates, extract_legal_refs, extract_parties_by_regex, extract_values
from .models import StructuredData
from .nlp import extract_entities_light, get_nlp_version
from .ocr import extract_text
from .sync import enqueue_pending
from .text_cleaner import clean_text

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
EDGE_CACHE_DIR = PROJECT_ROOT / "data" / "edge_cache"
PENDING_DIR = PROJECT_ROOT / "data" / "pending_sync"
LOCAL_FALLBACK_MARKERS = (
    "Análise local por regras concluída.",
    "Esta análise foi feita localmente, sem LLM",
)


def _is_local_fallback_result(result: dict) -> bool:
    summary = str(result.get("summary", ""))
    simplified_explanation = str(result.get("simplified_explanation", ""))
    return any(marker in summary or marker in simplified_explanation for marker in LOCAL_FALLBACK_MARKERS)


def process_document(file_path: Path) -> StructuredData:
    raw_text = extract_text(file_path)
    cleaned = clean_text(raw_text)

    parties = extract_parties_by_regex(cleaned)
    dates = extract_dates(cleaned)
    values = extract_values(cleaned)
    legal_refs = extract_legal_refs(cleaned)
    doc_type = classify_document(cleaned)
    entities = extract_entities_light(cleaned)

    return StructuredData(
        document_name=file_path.name,
        raw_text=raw_text,
        cleaned_text=cleaned,
        parties=parties,
        dates=dates,
        monetary_values=values,
        legal_refs=legal_refs,
        document_type=doc_type,
        entities=entities,
        extraction_version=f"regex-v3|{get_nlp_version()}",
    )


def save_structured_json(payload: StructuredData, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("JSON estruturado salvo em %s", out_path)


def send_to_backend(payload: StructuredData) -> dict:
    cached = load_cache(EDGE_CACHE_DIR, payload.cleaned_text)
    if cached:
        if _is_local_fallback_result(cached):
            logger.info("Cache local do edge contém fallback local; ignorando para reprocessar no backend")
        else:
            logger.info("Cache local do edge encontrado para o documento")
            return {**cached, "edge_cache_hit": True}

    endpoint = f"{settings.backend_url.rstrip('/')}/api/analyze"
    try:
        response = requests.post(
            endpoint,
            json=payload.to_dict(),
            timeout=settings.request_timeout_sec,
        )
        response.raise_for_status()
        result = response.json()
        if not _is_local_fallback_result(result) and not result.get("queued_for_sync", False):
            save_cache(EDGE_CACHE_DIR, payload.cleaned_text, result)
        else:
            logger.info("Resposta recebida sem cache local (fallback local ou fila de sincronização)")
        logger.info("Resposta recebida do backend")
        return result
    except Exception as exc:
        enqueue_pending(PENDING_DIR, payload)
        logger.warning("Falha ao enviar ao backend; payload enfileirado. Erro: %s", exc)
        return {
            "summary": "Backend indisponível no momento. Documento enfileirado para sincronização.",
            "risks": ["Análise avançada pendente por indisponibilidade de conectividade/backend."],
            "simplified_explanation": "A extração local foi concluída. Quando o backend voltar, execute sincronização das pendências.",
            "structured_json": payload.to_dict(),
            "cache_hit": False,
            "queued_for_sync": True,
        }
