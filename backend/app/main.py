import hashlib
import json
import logging
import tempfile
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .database import Base, engine, get_db
from .config import settings
from .edge_processor import process_document
from .llm import analyze_with_llm
from .logger import configure_logging
from .models import DocumentAnalysis
from .schemas import AnalysisOutput, StructuredInput
from .storage import ensure_bucket_exists, upload_structured_json

configure_logging()
logger = logging.getLogger(__name__)

LEGACY_RISK_MESSAGES = {
    "Análise jurídica avançada indisponível no modo offline/cloud desativado.",
    "Resposta do LLM em formato não estruturado; usando riscos locais por regras.",
    "A LLM retornou resposta parcial; valide manualmente os principais pontos do documento.",
}

LOCAL_FALLBACK_MARKERS = {
    "Análise local por regras concluída.",
    "Esta análise foi feita localmente, sem LLM",
}

app = FastAPI(title="EdgeAI Legal Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_event() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_bucket_exists()

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}

def _run_analysis(payload: StructuredInput, db: Session) -> AnalysisOutput:
    structured_json = payload.model_dump()
    document_hash = hashlib.sha256(payload.cleaned_text.encode("utf-8")).hexdigest()

    cached = db.query(DocumentAnalysis).filter(DocumentAnalysis.document_hash == document_hash).first()
    if cached:
        provider = (settings.llm_provider or "local").strip().lower()
        llm_enabled = (
            (provider == "openai" and bool(settings.openai_api_key))
            or (provider == "gemini" and bool(settings.gemini_api_key))
        )

        cached_risks = cached.risks_json.get("risks", []) if isinstance(cached.risks_json, dict) else []
        has_legacy_risk = any(risk in LEGACY_RISK_MESSAGES for risk in cached_risks)
        cached_summary = cached.summary or ""
        cached_explanation = cached.simplified_explanation or ""
        is_local_fallback_cached = any(marker in cached_summary for marker in LOCAL_FALLBACK_MARKERS) or any(
            marker in cached_explanation for marker in LOCAL_FALLBACK_MARKERS
        )
        should_reprocess_local_fallback = bool(llm_enabled and payload.raw_text and is_local_fallback_cached)
        should_reprocess_legacy = bool(llm_enabled and has_legacy_risk)

        if not should_reprocess_legacy and not should_reprocess_local_fallback:
            return AnalysisOutput(
                document_name=cached.document_name,
                summary=cached.summary,
                risks=cached_risks,
                simplified_explanation=cached.simplified_explanation,
                structured_json=cached.structured_json,
                cache_hit=True,
            )

        logger.info("Cache desatualizado/local detectado para %s; reprocessando análise.", payload.document_name)

    llm_result = analyze_with_llm(structured_json)

    s3_key = f"structured/{payload.document_name}-{document_hash[:10]}.json"
    upload_structured_json(s3_key, json.dumps(structured_json, ensure_ascii=False, indent=2))

    if cached:
        cached.document_name = payload.document_name
        cached.document_type = payload.document_type
        cached.raw_text = payload.raw_text
        cached.structured_json = structured_json
        cached.summary = llm_result["summary"]
        cached.risks_json = {"risks": llm_result["risks"]}
        cached.simplified_explanation = llm_result["simplified_explanation"]
        cached.s3_key = s3_key
        db.commit()

        logger.info("Análise atualizada para %s", payload.document_name)

        return AnalysisOutput(
            document_name=payload.document_name,
            summary=llm_result["summary"],
            risks=llm_result["risks"],
            simplified_explanation=llm_result["simplified_explanation"],
            structured_json=structured_json,
            cache_hit=False,
        )

    record = DocumentAnalysis(
        document_name=payload.document_name,
        document_hash=document_hash,
        document_type=payload.document_type,
        raw_text=payload.raw_text,
        structured_json=structured_json,
        summary=llm_result["summary"],
        risks_json={"risks": llm_result["risks"]},
        simplified_explanation=llm_result["simplified_explanation"],
        s3_key=s3_key,
    )

    db.add(record)
    db.commit()

    logger.info("Análise concluída para %s", payload.document_name)

    return AnalysisOutput(
        document_name=payload.document_name,
        summary=llm_result["summary"],
        risks=llm_result["risks"],
        simplified_explanation=llm_result["simplified_explanation"],
        structured_json=structured_json,
        cache_hit=False,
    )


@app.post("/api/analyze", response_model=AnalysisOutput)
def analyze(payload: StructuredInput, db: Session = Depends(get_db)) -> AnalysisOutput:
    return _run_analysis(payload, db)


@app.post("/api/process-file", response_model=AnalysisOutput)
async def process_file(file: UploadFile = File(...), db: Session = Depends(get_db)) -> AnalysisOutput:
    suffix = Path(file.filename or "documento.pdf").suffix.lower()
    if suffix not in {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}:
        raise HTTPException(status_code=400, detail="Formato não suportado. Envie PDF ou imagem.")

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
        temp_file.write(await file.read())
        temp_path = Path(temp_file.name)

    try:
        structured = process_document(temp_path)
        structured["document_name"] = file.filename or structured["document_name"]
        payload = StructuredInput(**structured)
        return _run_analysis(payload, db)
    except Exception as exc:
        logger.exception("Falha no processamento de arquivo")
        raise HTTPException(status_code=500, detail=f"Falha no processamento: {exc}") from exc
    finally:
        temp_path.unlink(missing_ok=True)
