from dataclasses import dataclass, asdict
from typing import Dict, List


@dataclass
class StructuredData:
    document_name: str
    raw_text: str
    cleaned_text: str
    parties: List[str]
    dates: List[str]
    monetary_values: List[str]
    legal_refs: List[str]
    document_type: str
    entities: Dict[str, List[str]]
    extraction_version: str

    def to_dict(self) -> Dict:
        return asdict(self)
