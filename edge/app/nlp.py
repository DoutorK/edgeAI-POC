import logging
import re
from typing import Dict, List

import spacy

from .config import settings

logger = logging.getLogger(__name__)

_NLP = None
_NLP_MODEL_NAME = "unknown"
_STOP_ENTITIES = {
    "art", "lei", "tribunal", "federal", "relator", "presidente", "supremo", "recurso"
}


def _get_nlp():
    global _NLP, _NLP_MODEL_NAME
    if _NLP is not None:
        return _NLP

    candidates = [settings.spacy_model, "pt_core_news_sm", "en_core_web_sm"]
    tried = set()
    for model_name in candidates:
        if model_name in tried:
            continue
        tried.add(model_name)
        try:
            _NLP = spacy.load(model_name)
            _NLP_MODEL_NAME = model_name
            logger.info("spaCy carregado com modelo %s", model_name)
            return _NLP
        except Exception:
            logger.warning("Falha ao carregar modelo spaCy '%s'. Tentando próximo fallback.", model_name)

    logger.warning("Nenhum modelo spaCy disponível. Usando pipeline em branco pt.")
    _NLP = spacy.blank("pt")
    _NLP_MODEL_NAME = "blank:pt"
    return _NLP


def extract_entities_light(cleaned_text: str) -> Dict[str, List[str]]:
    nlp = _get_nlp()
    doc = nlp(cleaned_text[:100000])

    people = sorted({_clean_entity(ent.text) for ent in doc.ents if ent.label_ in {"PER", "PERSON"}})
    orgs = sorted({_clean_entity(ent.text) for ent in doc.ents if ent.label_ in {"ORG"}})
    places = sorted({_clean_entity(ent.text) for ent in doc.ents if ent.label_ in {"LOC", "GPE"}})

    return {
        "people": [p for p in people if _is_valid_entity(p)],
        "organizations": [o for o in orgs if _is_valid_entity(o)],
        "locations": [l for l in places if _is_valid_entity(l)],
    }


def _clean_entity(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip(" -–—.,;:()[]{}\"'“”`´")
    return value


def _is_valid_entity(value: str) -> bool:
    if not value or len(value) < 4 or len(value) > 60:
        return False
    lowered = value.lower()
    if lowered in _STOP_ENTITIES:
        return False
    if any(char.isdigit() for char in value):
        return False
    alpha_count = sum(1 for char in value if char.isalpha())
    if alpha_count < 4:
        return False
    if alpha_count / max(len(value), 1) < 0.65:
        return False
    if len(value.split()) > 5:
        return False
    return True


def get_nlp_version() -> str:
    _get_nlp()
    return f"spacy:{_NLP_MODEL_NAME}"
