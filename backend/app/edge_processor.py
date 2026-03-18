import io
import re
import shutil
from pathlib import Path
from typing import Dict, List

import fitz
import pytesseract
from pdf2image import convert_from_path
from PIL import Image

from .config import settings

DATE_PATTERN = re.compile(r"\b(?:\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{4}[./-]\d{2}[./-]\d{2})\b")
VALUE_PATTERN = re.compile(
    r"(?:R\$\s?|US\$\s?|\$\s?)\d{1,3}(?:[\.,]\d{3})*(?:[\.,]\d{2})"
    r"|\b\d{1,3}(?:\.\d{3})+,\d{2}\b"
)
LEGAL_REF_PATTERN = re.compile(r"\b(?:art\.?\s?\d+(?:\.\d+)*[A-Za-z-]*|lei\s?n[ºo]?\s?\d+[\d\./-]*)\b", re.IGNORECASE)


def _apply_tesseract_path() -> None:
    if getattr(settings, "tesseract_cmd", ""):
        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd
        return

    which_path = shutil.which("tesseract")
    if which_path:
        pytesseract.pytesseract.tesseract_cmd = which_path
        return

    windows_candidates = [
        Path("C:/Program Files/Tesseract-OCR/tesseract.exe"),
        Path("C:/Program Files (x86)/Tesseract-OCR/tesseract.exe"),
    ]
    for candidate in windows_candidates:
        if candidate.exists():
            pytesseract.pytesseract.tesseract_cmd = str(candidate)
            return


def _extract_pdf_text(file_path: Path) -> str:
    try:
        pages: List[Image.Image] = convert_from_path(str(file_path), dpi=200)
        return "\n".join(pytesseract.image_to_string(page, lang="por+eng") for page in pages)
    except Exception:
        text_parts: List[str] = []
        with fitz.open(file_path) as document:
            for page in document:
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                image = Image.open(io.BytesIO(pix.tobytes("png")))
                text_parts.append(pytesseract.image_to_string(image, lang="por+eng"))
        return "\n".join(text_parts)


def _extract_image_text(file_path: Path) -> str:
    image = Image.open(file_path)
    return pytesseract.image_to_string(image, lang="por+eng")


def _clean_text(text: str) -> str:
    normalized = re.sub(r"\r\n?", "\n", text)
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{2,}", "\n", normalized)
    return normalized.strip()


def _classify_document(cleaned_text: str) -> str:
    text = cleaned_text.lower()
    keyword_map = {
        "peticao_inicial": ["petição inicial", "requer a citação", "dos fatos"],
        "contrato": ["contrato", "cláusula", "contratante", "contratada"],
        "sentenca": ["sentença", "julgo procedente", "dispositivo"],
        "acordao": ["acórdão", "voto", "turma julgadora"],
    }

    best_label = "indefinido"
    best_score = 0
    for label, terms in keyword_map.items():
        score = sum(1 for term in terms if term in text)
        if score > best_score:
            best_score = score
            best_label = label
    return best_label


def process_document(file_path: Path) -> Dict:
    _apply_tesseract_path()
    suffix = file_path.suffix.lower()
    raw_text = _extract_pdf_text(file_path) if suffix == ".pdf" else _extract_image_text(file_path)
    cleaned_text = _clean_text(raw_text)

    return {
        "document_name": file_path.name,
        "raw_text": raw_text,
        "cleaned_text": cleaned_text,
        "parties": [],
        "dates": sorted(set(DATE_PATTERN.findall(cleaned_text))),
        "monetary_values": sorted(set(value.strip() for value in VALUE_PATTERN.findall(cleaned_text))),
        "legal_refs": sorted(set(match.strip() for match in LEGAL_REF_PATTERN.findall(cleaned_text))),
        "document_type": _classify_document(cleaned_text),
        "entities": {"people": [], "organizations": [], "locations": []},
        "extraction_version": "visual-ingest-v1",
    }
