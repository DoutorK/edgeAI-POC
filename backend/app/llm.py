import json
import importlib
import re
import logging
from typing import List

from .config import settings


logger = logging.getLogger(__name__)


def _top_items(values: List[str], limit: int = 4) -> str:
    if not values:
        return "nenhum"
    normalized = [str(value).strip() for value in values if str(value).strip()]
    if not normalized:
        return "nenhum"
    return ", ".join(normalized[:limit])


def _top_entities(entities: dict, limit: int = 3) -> str:
    if not isinstance(entities, dict):
        return "nenhuma"
    merged: List[str] = []
    for key in ("people", "organizations", "locations"):
        merged.extend(entities.get(key, []) or [])
    cleaned = [str(value).strip() for value in merged if str(value).strip()]
    if not cleaned:
        return "nenhuma"
    unique = list(dict.fromkeys(cleaned))
    return ", ".join(unique[:limit])


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

    dates = compact.get("dates", [])
    monetary_values = compact.get("monetary_values", [])
    legal_refs = compact.get("legal_refs", [])
    parties = compact.get("parties", [])
    entities = compact.get("entities", {})
    snippets = compact.get("relevant_snippets", [])

    summary_parts = [
        f"Tipo: {compact.get('document_type', 'indefinido')}",
        f"Datas detectadas: {len(dates)} (ex.: {_top_items(dates)})",
        f"Valores detectados: {len(monetary_values)} (ex.: {_top_items(monetary_values)})",
        f"Referências legais: {len(legal_refs)} (ex.: {_top_items(legal_refs)})",
        f"Partes detectadas: {len(parties)} (ex.: {_top_items(parties)})",
        f"Entidades detectadas: {_top_entities(entities)}",
        f"Riscos sinalizados: {len(risks)}",
    ]

    suggested_actions: List[str] = []
    if dates:
        suggested_actions.append("Monte uma linha do tempo com as datas extraídas e valide marcos de prazo processual.")
    else:
        suggested_actions.append("Revise OCR/texto original para localizar datas que possam não ter sido capturadas.")

    if legal_refs:
        suggested_actions.append("Confirme pertinência dos artigos/leis extraídos ao pedido principal e à causa de pedir.")
    else:
        suggested_actions.append("Busque no documento fundamentos normativos (artigos/leis) para reforçar a base jurídica.")

    if not monetary_values and any(token in lowered_text for token in ["valor", "pagamento", "indeniza", "multa"]):
        suggested_actions.append("Há indícios financeiros sem valor estruturado; validar cláusulas de multa, juros e atualização.")
    elif monetary_values:
        suggested_actions.append("Valide se os valores extraídos estão atualizados e com a moeda correta.")

    key_excerpt = snippets[0] if snippets else "Nenhum trecho relevante foi selecionado automaticamente."

    return {
        "summary": "Análise local por regras concluída. " + " | ".join(summary_parts),
        "risks": risks[:8],
        "simplified_explanation": (
            "Análise executada localmente (sem LLM) com heurísticas jurídicas. "
            f"Trecho-chave identificado: \"{key_excerpt[:260]}\". "
            "Próximos passos recomendados: "
            + " ".join(f"{index + 1}) {action}" for index, action in enumerate(suggested_actions[:4]))
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


def _extract_json_content(content: str) -> dict:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    fenced_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, flags=re.DOTALL)
    if fenced_match:
        return json.loads(fenced_match.group(1))

    object_match = re.search(r"(\{.*\})", content, flags=re.DOTALL)
    if object_match:
        return json.loads(object_match.group(1))

    raise json.JSONDecodeError("Não foi possível extrair JSON", content, 0)


def _analyze_with_openai(structured_json: dict) -> str:
    openai_module = importlib.import_module("openai")
    OpenAI = openai_module.OpenAI
    client = OpenAI(api_key=settings.openai_api_key, max_retries=0)
    response = client.responses.create(
        model=settings.llm_model,
        input=build_prompt(structured_json),
        temperature=0.2,
        max_output_tokens=700,
    )
    return (response.output_text or "").strip()


def _analyze_with_gemini(structured_json: dict) -> str:
    gemini_module = importlib.import_module("google.generativeai")
    gemini_module.configure(api_key=settings.gemini_api_key)
    model = gemini_module.GenerativeModel(settings.gemini_model)
    response = model.generate_content(
        build_prompt(structured_json),
        generation_config={"temperature": 0.2, "max_output_tokens": 700},
    )
    return (getattr(response, "text", "") or "").strip()


def _fallback_with_error(structured_json: dict, exc: Exception) -> dict:
    logger.warning("Falha ao consultar LLM (%s): %s. Aplicando fallback local.", type(exc).__name__, exc)
    local_result = analyze_locally(structured_json)
    error_code = getattr(exc, "code", None)
    error_suffix = f" código={error_code}" if error_code else ""
    risks = [
        f"LLM indisponível no momento ({type(exc).__name__}{error_suffix}); análise local aplicada.",
        *local_result["risks"],
    ]
    return {
        "summary": local_result["summary"],
        "risks": risks[:8],
        "simplified_explanation": (
            "A análise por LLM não pôde ser concluída (ex.: quota, rede ou credenciais). "
            + local_result["simplified_explanation"]
        ),
    }


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
    provider = (settings.llm_provider or "openai").strip().lower()

    if provider == "gemini" and not settings.gemini_api_key:
        return analyze_locally(structured_json)
    if provider == "openai" and not settings.openai_api_key:
        return analyze_locally(structured_json)

    content = ""
    try:
        if provider == "gemini":
            content = _analyze_with_gemini(structured_json)
        elif provider == "openai":
            content = _analyze_with_openai(structured_json)
        else:
            raise ValueError(f"LLM_PROVIDER inválido: {settings.llm_provider}. Use 'openai' ou 'gemini'.")
    except Exception as exc:
        return _fallback_with_error(structured_json, exc)

    try:
        parsed = _extract_json_content(content)
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
