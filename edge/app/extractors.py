import re
from datetime import datetime
from typing import List


DATE_PATTERN = re.compile(r"\b(?:\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{4}[./-]\d{2}[./-]\d{2})\b")
VALUE_PATTERN = re.compile(
    r"(?:R\$\s?|US\$\s?|\$\s?)\d{1,3}(?:[\.,]\d{3})*(?:[\.,]\d{2})"
    r"|\b\d{1,3}(?:\.\d{3})+,\d{2}\b"
)
LEGAL_REF_PATTERN = re.compile(r"\b(?:art\.?\s?\d+(?:\.\d+)*[A-Za-z-]*|lei\s?n[ºo]?\s?\d+[\d\./-]*)\b", re.IGNORECASE)


def extract_dates(text: str) -> List[str]:
    candidates = sorted(set(DATE_PATTERN.findall(text)))
    valid_dates: List[str] = []
    for candidate in candidates:
        normalized = candidate.replace(".", "/").replace("-", "/")
        parts = normalized.split("/")
        try:
            if len(parts[0]) == 4:
                year, month, day = map(int, parts)
            else:
                day, month, year = map(int, parts)
                if year < 100:
                    year += 1900
            datetime(year, month, day)
            valid_dates.append(candidate)
        except Exception:
            continue
    return valid_dates


def extract_values(text: str) -> List[str]:
    values = [value.strip() for value in VALUE_PATTERN.findall(text)]
    return sorted(set(values))


def extract_legal_refs(text: str) -> List[str]:
    return sorted(set(match.strip() for match in LEGAL_REF_PATTERN.findall(text)))


def extract_parties_by_regex(text: str) -> List[str]:
    party_markers = [
        r"Autor(?:a)?\s*:\s*([A-ZÀ-Ú\s]{3,})",
        r"Réu(?:s)?\s*:\s*([A-ZÀ-Ú\s]{3,})",
        r"Requerente\s*:\s*([A-ZÀ-Ú\s]{3,})",
        r"Requerido\s*:\s*([A-ZÀ-Ú\s]{3,})",
    ]
    parties: List[str] = []
    for pattern in party_markers:
        matches = re.findall(pattern, text, flags=re.IGNORECASE)
        parties.extend(match.strip() for match in matches)
    return sorted(set(parties))
