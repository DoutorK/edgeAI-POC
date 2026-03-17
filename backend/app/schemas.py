from pydantic import BaseModel, Field
from typing import Dict, List


class StructuredInput(BaseModel):
    document_name: str
    raw_text: str
    cleaned_text: str
    parties: List[str]
    dates: List[str]
    monetary_values: List[str]
    legal_refs: List[str]
    document_type: str
    entities: Dict[str, List[str]] = Field(default_factory=dict)
    extraction_version: str = "regex-v1"


class AnalysisOutput(BaseModel):
    document_name: str
    summary: str
    risks: List[str]
    simplified_explanation: str
    structured_json: dict
    cache_hit: bool = False
