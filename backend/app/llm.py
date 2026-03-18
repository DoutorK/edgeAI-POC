import json
import importlib
import re
import logging
from typing import List

from .config import settings


logger = logging.getLogger(__name__)


def _normalize_text(value: str, max_chars: int = 180) -> str:
    cleaned = str(value or "").replace("\x00", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:max_chars]


def _normalize_list(values, max_items: int = 40, max_chars_per_item: int = 180) -> List[str]:
    if not isinstance(values, list):
        return []
    normalized: List[str] = []
    for raw in values:
        item = _normalize_text(raw, max_chars_per_item)
        if not item:
            continue
        normalized.append(item)
        if len(normalized) >= max_items:
            break
    return normalized


def _normalize_entities(entities: dict) -> dict:
    if not isinstance(entities, dict):
        return {"people": [], "organizations": [], "locations": []}
    max_items = max(1, int(settings.llm_max_items_per_list))
    max_item_chars = max(40, int(settings.llm_max_item_chars))
    return {
        "people": _normalize_list(entities.get("people", []), max_items=max_items, max_chars_per_item=max_item_chars),
        "organizations": _normalize_list(
            entities.get("organizations", []), max_items=max_items, max_chars_per_item=max_item_chars
        ),
        "locations": _normalize_list(entities.get("locations", []), max_items=max_items, max_chars_per_item=max_item_chars),
    }


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
    compact_json = json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
    return (
        "Você é um assistente jurídico para análise preliminar de documentos. "
        "Retorne preferencialmente em JSON válido com as chaves: summary (string), risks (lista de strings), simplified_explanation (string). "
        "Não inclua aconselhamento definitivo e destaque incertezas. "
        "Evite aconselhamento definitivo e destaque incertezas.\n\n"
        f"Contexto jurídico essencial: {compact_json}"
    )


def build_retry_prompt(structured_json: dict) -> str:
    compact = build_compact_context(structured_json)
    minimal = {
        "document_name": compact.get("document_name", ""),
        "document_type": compact.get("document_type", "indefinido"),
        "dates": compact.get("dates", [])[:8],
        "monetary_values": compact.get("monetary_values", [])[:8],
        "legal_refs": compact.get("legal_refs", [])[:12],
        "parties": compact.get("parties", [])[:8],
        "relevant_snippets": compact.get("relevant_snippets", [])[:3],
    }
    minimal_json = json.dumps(minimal, ensure_ascii=False, separators=(",", ":"))
    return (
        "Retorne SOMENTE JSON válido sem markdown no formato exato: "
        "{\"summary\":\"...\",\"risks\":[\"...\"],\"simplified_explanation\":\"...\"}. "
        "summary com 300-500 caracteres, risks com 3 a 5 itens curtos, "
        "simplified_explanation com 200-350 caracteres.\n"
        f"Contexto resumido: {minimal_json}"
    )


def build_compact_context(structured_json: dict) -> dict:
    cleaned_text = _normalize_text(
        structured_json.get("cleaned_text", ""),
        max_chars=max(800, int(settings.llm_cleaned_text_max_chars)),
    )
    max_items = max(1, int(settings.llm_max_items_per_list))
    max_item_chars = max(40, int(settings.llm_max_item_chars))
    parties = _normalize_list(structured_json.get("parties", []), max_items=max_items, max_chars_per_item=max_item_chars)
    dates = _normalize_list(structured_json.get("dates", []), max_items=max_items, max_chars_per_item=max_item_chars)
    monetary_values = _normalize_list(
        structured_json.get("monetary_values", []), max_items=max_items, max_chars_per_item=max_item_chars
    )
    legal_refs = _normalize_list(structured_json.get("legal_refs", []), max_items=max_items, max_chars_per_item=max_item_chars)
    entities = _normalize_entities(structured_json.get("entities", {}))

    compact = {
        "document_name": _normalize_text(structured_json.get("document_name", ""), max_chars=120),
        "document_type": _normalize_text(structured_json.get("document_type", "indefinido"), max_chars=60) or "indefinido",
        "parties": parties,
        "dates": dates,
        "monetary_values": monetary_values,
        "legal_refs": legal_refs,
        "entities": entities,
        "extraction_version": _normalize_text(structured_json.get("extraction_version", ""), max_chars=80),
        "relevant_snippets": extract_relevant_snippets(
            cleaned_text,
            max_snippets=max(1, int(settings.llm_max_snippets)),
            max_total_chars=max(300, int(settings.llm_max_snippets_total_chars)),
        ),
    }
    return compact


def _extract_json_content(content: str) -> dict:
    def _find_balanced_json_object(text: str) -> str:
        start = text.find("{")
        if start == -1:
            return ""

        depth = 0
        in_string = False
        escape = False

        for index in range(start, len(text)):
            char = text[index]

            if in_string:
                if escape:
                    escape = False
                    continue
                if char == "\\":
                    escape = True
                    continue
                if char == '"':
                    in_string = False
                continue

            if char == '"':
                in_string = True
                continue
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start : index + 1]

        return ""

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    cleaned = content.strip().lstrip("\ufeff")
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    for candidate_text in (cleaned, content):
        candidate = _find_balanced_json_object(candidate_text)
        if candidate:
            return json.loads(candidate)

    raise json.JSONDecodeError("Não foi possível extrair JSON", content, 0)


def _extract_partial_fields(content: str) -> dict:
    def _clean(value: str) -> str:
        cleaned = value.strip()
        cleaned = cleaned.replace('\\n', ' ').replace('\\t', ' ')
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned.strip(' "')

    summary_match = re.search(r'"summary"\s*:\s*"(.*?)"', content, flags=re.DOTALL)
    if not summary_match:
        summary_match = re.search(r'"summary"\s*:\s*"([^\n\r]*)', content, flags=re.DOTALL)

    simplified_match = re.search(r'"simplified_explanation"\s*:\s*"(.*?)"', content, flags=re.DOTALL)
    if not simplified_match:
        simplified_match = re.search(r'"simplified_explanation"\s*:\s*"([^\n\r]*)', content, flags=re.DOTALL)

    risks_block_match = re.search(r'"risks"\s*:\s*\[(.*?)\]', content, flags=re.DOTALL)
    risks: List[str] = []
    if risks_block_match:
        risks = [_clean(match) for match in re.findall(r'"(.*?)"', risks_block_match.group(1), flags=re.DOTALL)]

    summary_value = _clean(summary_match.group(1)) if summary_match else ""
    simplified_value = _clean(simplified_match.group(1)) if simplified_match else ""

    if summary_value or simplified_value or risks:
        if not summary_value:
            summary_value = "Resumo parcial retornado pela LLM."
        if not simplified_value:
            simplified_value = "Explicação parcial retornada pela LLM; revise o conteúdo completo para validação."
        if not risks:
            risks = ["A LLM retornou resposta parcial; valide manualmente os principais pontos do documento."]

        return {
            "summary": summary_value,
            "risks": risks[:8],
            "simplified_explanation": simplified_value,
        }

    return {}


def _analyze_with_openai(structured_json: dict, prompt: str | None = None, max_output_tokens: int = 700) -> str:
    openai_module = importlib.import_module("openai")
    OpenAI = openai_module.OpenAI
    client = OpenAI(api_key=settings.openai_api_key, max_retries=0)
    response = client.responses.create(
        model=settings.llm_model,
        input=prompt or build_prompt(structured_json),
        temperature=0.2,
        max_output_tokens=max(128, int(max_output_tokens)),
    )
    return (response.output_text or "").strip()


def _analyze_with_gemini(structured_json: dict, prompt: str | None = None, max_output_tokens: int | None = None) -> str:
    def _extract_response_text(response) -> str:
        direct_text = getattr(response, "text", None)
        if direct_text:
            return str(direct_text).strip()

        candidates = getattr(response, "candidates", []) or []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            parts = getattr(content, "parts", None) if content else None
            if not parts:
                continue

            collected: List[str] = []
            for part in parts:
                part_text = getattr(part, "text", None)
                if part_text:
                    collected.append(str(part_text))

            if collected:
                return "\n".join(collected).strip()

        finish_reason = getattr(candidates[0], "finish_reason", None) if candidates else None
        raise RuntimeError(f"Gemini retornou sem conteúdo textual (finish_reason={finish_reason}).")

    gemini_module = importlib.import_module("google.generativeai")
    gemini_module.configure(api_key=settings.gemini_api_key)
    model = gemini_module.GenerativeModel(settings.gemini_model)
    response = model.generate_content(
        prompt or build_prompt(structured_json),
        generation_config={
            "temperature": 0.2,
            "max_output_tokens": max(128, int(max_output_tokens or settings.gemini_max_output_tokens)),
        },
    )
    return _extract_response_text(response)


def _analyze_with_gemini_segmented(structured_json: dict) -> dict:
    compact = build_compact_context(structured_json)
    compact_min = {
        "document_name": compact.get("document_name", ""),
        "document_type": compact.get("document_type", "indefinido"),
        "parties": compact.get("parties", [])[:6],
        "dates": compact.get("dates", [])[:8],
        "monetary_values": compact.get("monetary_values", [])[:6],
        "legal_refs": compact.get("legal_refs", [])[:10],
        "relevant_snippets": compact.get("relevant_snippets", [])[:2],
    }
    context = json.dumps(compact_min, ensure_ascii=False, separators=(",", ":"))

    summary_prompt = (
        "Com base no contexto, escreva um resumo jurídico preliminar em PT-BR com até 450 caracteres, em texto puro. "
        f"Contexto: {context}"
    )
    risks_prompt = (
        "Com base no contexto, retorne SOMENTE um JSON array com 3 a 5 riscos jurídicos curtos em PT-BR, sem texto extra. "
        f"Contexto: {context}"
    )
    simplified_prompt = (
        "Com base no contexto, escreva explicação simples para leigos em PT-BR com até 320 caracteres, em texto puro. "
        f"Contexto: {context}"
    )

    summary_text = _analyze_with_gemini(structured_json, prompt=summary_prompt, max_output_tokens=360)
    risks_text = _analyze_with_gemini(structured_json, prompt=risks_prompt, max_output_tokens=360)
    simplified_text = _analyze_with_gemini(structured_json, prompt=simplified_prompt, max_output_tokens=320)

    risks: List[str] = []

    def _clean_risk_item(value: str) -> str:
        text = str(value or "").strip()
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip().strip('"').strip()
        if text in {"{", "}", "[", "]", ","}:
            return ""
        if text.lower().startswith("json"):
            return ""
        return text

    try:
        risks = json.loads(risks_text)
        if not isinstance(risks, list):
            risks = []
    except Exception:
        risks = [line.strip(" -") for line in risks_text.splitlines() if line.strip()][:5]

    risks = [_clean_risk_item(risk) for risk in risks]
    risks = [risk for risk in risks if risk][:8]

    local_result = analyze_locally(structured_json)

    if not risks:
        risks = local_result["risks"][:5]

    summary = _normalize_text(summary_text, max_chars=700)
    simplified = _normalize_text(simplified_text, max_chars=500)

    if len(summary) < 100:
        summary = _normalize_text(f"{summary}. {local_result['summary']}", max_chars=700)
    if len(simplified) < 90:
        simplified = _normalize_text(f"{simplified}. {local_result['simplified_explanation']}", max_chars=500)

    return {
        "summary": summary,
        "risks": risks,
        "simplified_explanation": simplified,
    }


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


def _parse_llm_content(content: str, structured_json: dict) -> dict:
    try:
        parsed = _extract_json_content(content)
        return {
            "summary": parsed.get("summary", "Resumo não retornado"),
            "risks": parsed.get("risks", []),
            "simplified_explanation": parsed.get("simplified_explanation", "Explicação não retornada"),
        }
    except json.JSONDecodeError:
        partial = _extract_partial_fields(content)
        if partial:
            return partial

        local_result = analyze_locally(structured_json)
        return {
            "summary": content[:1200],
            "risks": ["Resposta do LLM em formato não estruturado; usando riscos locais por regras.", *local_result["risks"]],
            "simplified_explanation": "A resposta do LLM veio fora do formato esperado, então os riscos foram complementados por análise local.",
        }


def _is_partial_result(result: dict) -> bool:
    summary = str(result.get("summary", "") or "").strip()
    simplified = str(result.get("simplified_explanation", "") or "").strip().lower()
    risks = result.get("risks") or []

    if any("resposta parcial" in str(risk).lower() for risk in risks):
        return True
    if "parcial" in simplified:
        return True
    if summary.endswith("-"):
        return True
    if len(summary) < 80:
        return True
    return False


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

    if provider == "local":
        return analyze_locally(structured_json)

    if provider == "gemini" and not settings.gemini_api_key:
        return analyze_locally(structured_json)
    if provider == "openai" and not settings.openai_api_key:
        return analyze_locally(structured_json)

    if provider not in {"openai", "gemini", "local"}:
        logger.warning("LLM_PROVIDER inválido (%s). Aplicando análise local.", settings.llm_provider)
        return analyze_locally(structured_json)

    content = ""
    try:
        if provider == "gemini":
            content = _analyze_with_gemini(structured_json)
        elif provider == "openai":
            content = _analyze_with_openai(structured_json)
    except Exception as exc:
        return _fallback_with_error(structured_json, exc)

    result = _parse_llm_content(content, structured_json)
    if not _is_partial_result(result):
        return result

    logger.info("Resposta parcial da LLM detectada; tentando nova geração com prompt enxuto.")
    try:
        retry_prompt = build_retry_prompt(structured_json)
        if provider == "gemini":
            retry_content = _analyze_with_gemini(
                structured_json,
                prompt=retry_prompt,
                max_output_tokens=max(256, int(settings.gemini_max_output_tokens) * 2),
            )
        else:
            retry_content = _analyze_with_openai(
                structured_json,
                prompt=retry_prompt,
                max_output_tokens=1100,
            )

        retry_result = _parse_llm_content(retry_content, structured_json)
        if provider == "gemini" and _is_partial_result(retry_result):
            logger.info("Retry ainda parcial no Gemini; tentando geração segmentada.")
            return _analyze_with_gemini_segmented(structured_json)
        return retry_result
    except Exception as exc:
        logger.warning("Falha no retry de resposta parcial (%s): %s", type(exc).__name__, exc)
        return result
