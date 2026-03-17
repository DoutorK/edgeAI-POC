import logging
import io
import shutil
from pathlib import Path
from typing import List

import fitz
import pytesseract
from pdf2image import convert_from_path
from PIL import Image

from .config import settings

logger = logging.getLogger(__name__)


def _apply_tesseract_path() -> None:
    if settings.tesseract_cmd:
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


def _ensure_tesseract_ready() -> None:
    _apply_tesseract_path()
    try:
        pytesseract.get_tesseract_version()
    except Exception as exc:
        raise RuntimeError(
            "Tesseract OCR não encontrado. Instale o Tesseract e/ou defina TESSERACT_CMD. "
            "Exemplo no Windows: C:/Program Files/Tesseract-OCR/tesseract.exe"
        ) from exc


def extract_text(file_path: Path) -> str:
    _ensure_tesseract_ready()
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(file_path)
    return _extract_image(file_path)


def _extract_pdf(file_path: Path) -> str:
    logger.info("Executando OCR para PDF: %s", file_path)
    try:
        pages: List[Image.Image] = convert_from_path(str(file_path), dpi=200)
        text_parts = [pytesseract.image_to_string(page, lang="por+eng") for page in pages]
        return "\n".join(text_parts)
    except Exception as exc:
        logger.warning("pdf2image indisponível (poppler ausente?). Usando fallback PyMuPDF. Erro: %s", exc)
        text_parts = _extract_pdf_with_pymupdf(file_path)
    return "\n".join(text_parts)


def _extract_pdf_with_pymupdf(file_path: Path) -> List[str]:
    text_parts: List[str] = []
    with fitz.open(file_path) as document:
        for page in document:
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            image = Image.open(io.BytesIO(pix.tobytes("png")))
            text_parts.append(pytesseract.image_to_string(image, lang="por+eng"))
    return text_parts


def _extract_image(file_path: Path) -> str:
    logger.info("Executando OCR para imagem: %s", file_path)
    image = Image.open(file_path)
    return pytesseract.image_to_string(image, lang="por+eng")
