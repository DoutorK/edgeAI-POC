import json
import importlib
import re
from typing import List

from .config import settings


def analyze_locally(structured_json: dict) -> dict:
    compact = build_compact_context(structured_json)
    cleaned_text = structured_json.get("cleaned_text", "")
    lowered_text = cleaned_text.lower()

    risks: List[str] = []

    if compact.get("document_type") == "indefinido":
        risks.append("Tipo documental indefinido: exige validação manual da natureza jurídica do documento.")

    if not compact.get("legal_refs"):
        risks.append("Ausência de referência legal explícita (ex.: artigo/lei), o que pode enfraquecer fundamentação.")

    if not compact.get("dates"):
        risks.append("Nenhuma data identificada: possível risco de perda de prazo e dificuldade de reconstrução cronológica.")

    if not compact.get("monetary_values") and any(token in lowered_text for token in ["valor", "pagamento", "indeniza", "multa"]):
        risks.append("Há menção financeira sem valores claros extraídos; revisar cláusulas de valor, multa e atualização.")

    if any(token in lowered_text for token in ["liminar", "tutela de urg", "urgência", "inaudita altera parte"]):
        risks.append("Indícios de urgência processual: confirmar requisitos e prazos para medida urgente.")

    if any(token in lowered_text for token in ["rescis", "inadimpl", "mora", "descumpr", "penalidade", "multa"]):
        risks.append("Há sinais de inadimplemento/rescisão/penalidade; verificar impacto contratual e prova documental.")

    if any(token in lowered_text for token in ["prescri", "decad", "prazo prescricional"]):
        risks.append("Menção a prescrição/decadência: revisar marcos temporais para evitar perda de direito.")

    if len(compact.get("relevant_snippets", [])) <= 2:
        risks.append("Pouco conteúdo jurídico relevante detectado automaticamente; qualidade do OCR pode estar limitada.")

    if not risks:
        risks.append("Sem risco crítico evidente por regras locais; recomenda-se revisão humana para confirmação jurídica.")

    summary_parts = [
        f"Tipo: {compact.get('document_type', 'indefinido')}",
        f"Datas detectadas: {len(compact.get('dates', []))}",
        f"Valores detectados: {len(compact.get('monetary_values', []))}",
        f"Referências legais: {len(compact.get('legal_refs', []))}",
        f"Riscos sinalizados: {len(risks)}",
    ]

    return {
        "summary": "Análise local por regras concluída. " + " | ".join(summary_parts),
        "risks": risks[:8],
        "simplified_explanation": (
            "Esta análise foi feita localmente, sem LLM, com heurísticas sobre datas, valores, "
            "referências legais, urgência e inadimplemento. Trate os resultados como triagem inicial."
        ),
    }


def build_prompt(structured_json: dict) -> str:
    compact = build_compact_context(structured_json)
    return (
        "Você é um assistente jurídico para análise preliminar de documentos. "
        "Retorne JSON com as chaves: summary, risks (lista), simplified_explanation. "
        "Evite aconselhamento definitivo e destaque incertezas.\n\n"
        f"Contexto jurídico essencial:\n{json.dumps(compact, ensure_ascii=False, indent=2)}"
    )


def build_compact_context(structured_json: dict) -> dict:
    cleaned_text = structured_json.get("cleaned_text", "")
    compact = {
        "document_name": structured_json.get("document_name", ""),
        "document_type": structured_json.get("document_type", "indefinido"),
        "parties": structured_json.get("parties", []),
        "dates": structured_json.get("dates", []),
        "monetary_values": structured_json.get("monetary_values", []),
        "legal_refs": structured_json.get("legal_refs", []),
        "entities": structured_json.get("entities", {}),
        "extraction_version": structured_json.get("extraction_version", ""),
        "relevant_snippets": extract_relevant_snippets(cleaned_text),
    }
    return compact


def extract_relevant_snippets(cleaned_text: str, max_snippets: int = 12, max_total_chars: int = 2400) -> List[str]:
    if not cleaned_text:
        return []

    keyword_pattern = re.compile(
        r"\b(art\.?|lei|contrato|cláusula|sentença|acórdão|recurso|autor|réu|requerente|requerido|valor|r\$|us\$|custas|prazo|prescri)\w*\b",
        re.IGNORECASE,
    )

    lines = [line.strip() for line in cleaned_text.splitlines() if line.strip()]
    selected: List[str] = []
    total_chars = 0

    for line in lines:
        if len(line) < 25:
            continue
        has_keyword = bool(keyword_pattern.search(line))
        has_number = bool(re.search(r"\d", line))
        if not has_keyword and not has_number:
            continue

        alpha_count = sum(1 for char in line if char.isalpha())
        if alpha_count < 10:
            continue

        clean_line = re.sub(r"\s+", " ", line)
        if clean_line in selected:
            continue

        if total_chars + len(clean_line) > max_total_chars:
            break

        selected.append(clean_line)
        total_chars += len(clean_line)

        if len(selected) >= max_snippets:
            break

    if not selected:
        fallback = " ".join(lines[:6])
        return [fallback[:max_total_chars]] if fallback else []

    return selected


def analyze_with_llm(structured_json: dict) -> dict:
    if not settings.openai_api_key:
        return analyze_locally(structured_json)

    try:
        openai_module = importlib.import_module("openai")
        OpenAI = openai_module.OpenAI
    except Exception:
        return analyze_locally(structured_json)

    client = OpenAI(api_key=settings.openai_api_key)
    response = client.responses.create(
        model=settings.llm_model,
        input=build_prompt(structured_json),
        temperature=0.2,
        max_output_tokens=700,
    )

    content = response.output_text.strip()
    try:
        parsed = json.loads(content)
        return {
            "summary": parsed.get("summary", "Resumo não retornado"),
            "risks": parsed.get("risks", []),
            "simplified_explanation": parsed.get("simplified_explanation", "Explicação não retornada"),
        }
    except json.JSONDecodeError:
        local_result = analyze_locally(structured_json)
        return {
            "summary": content[:1200],
            "risks": ["Resposta do LLM em formato não estruturado; usando riscos locais por regras.", *local_result["risks"]],
            "simplified_explanation": "A resposta do LLM veio fora do formato esperado, então os riscos foram complementados por análise local.",
        }
