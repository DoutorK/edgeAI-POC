import hashlib
import json
import logging
from fastapi import Depends, FastAPI
from sqlalchemy.orm import Session

from .database import Base, engine, get_db
from .llm import analyze_with_llm
from .logger import configure_logging
from .models import DocumentAnalysis
from .schemas import AnalysisOutput, StructuredInput
from .storage import ensure_bucket_exists, upload_structured_json

configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="EdgeAI Legal Backend", version="0.1.0")


@app.on_event("startup")
def startup_event() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_bucket_exists()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/analyze", response_model=AnalysisOutput)
def analyze(payload: StructuredInput, db: Session = Depends(get_db)) -> AnalysisOutput:
    structured_json = payload.model_dump()
    document_hash = hashlib.sha256(payload.cleaned_text.encode("utf-8")).hexdigest()

    cached = db.query(DocumentAnalysis).filter(DocumentAnalysis.document_hash == document_hash).first()
    if cached:
        return AnalysisOutput(
            document_name=cached.document_name,
            summary=cached.summary,
            risks=cached.risks_json.get("risks", []),
            simplified_explanation=cached.simplified_explanation,
            structured_json=cached.structured_json,
            cache_hit=True,
        )

    llm_result = analyze_with_llm(structured_json)

    s3_key = f"structured/{payload.document_name}-{document_hash[:10]}.json"
    upload_structured_json(s3_key, json.dumps(structured_json, ensure_ascii=False, indent=2))

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
