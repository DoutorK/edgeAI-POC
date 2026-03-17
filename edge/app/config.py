from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class EdgeSettings:
    tesseract_cmd: str = os.getenv("TESSERACT_CMD", "")
    backend_url: str = os.getenv("BACKEND_URL", "http://localhost:8000")
    request_timeout_sec: int = int(os.getenv("REQUEST_TIMEOUT_SEC", "45"))
    spacy_model: str = os.getenv("SPACY_MODEL", "pt_core_news_sm")


settings = EdgeSettings()
