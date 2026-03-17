from typing import List


def classify_document(cleaned_text: str, keywords: List[str] | None = None) -> str:
    text = cleaned_text.lower()
    keyword_map = {
        "peticao_inicial": ["petição inicial", "requer a citação", "dos fatos"],
        "contrato": ["contrato", "cláusula", "contratante", "contratada"],
        "sentenca": ["sentença", "julgo procedente", "dispositivo"],
        "acordao": ["acórdão", "voto", "turma julgadora"],
    }

    if keywords:
        keyword_map["custom"] = keywords

    best_label = "indefinido"
    best_score = 0
    for label, terms in keyword_map.items():
        score = sum(1 for term in terms if term in text)
        if score > best_score:
            best_score = score
            best_label = label
    return best_label
