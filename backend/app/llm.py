import json
import importlib
import re
import logging
from typing import List

from .config import settings


logger = logging.getLogger(__name__)


_STOPWORDS = {
    "a", "as", "ao", "aos", "a", "à", "às", "o", "os", "de", "da", "das", "do", "dos", "e", "em", "no", "na",
    "nos", "nas", "um", "uma", "uns", "umas", "por", "para", "com", "sem", "que", "se", "é", "ser", "foi", "são",
    "como", "ou", "não", "mais", "menos", "já", "sobre", "este", "esta", "esses", "essas", "isso", "isto", "ao",
}


def _token_set(text: str) -> set:
    normalized = re.sub(r"[^\w\s]", " ", str(text or "").lower(), flags=re.UNICODE)
    tokens = [token for token in normalized.split() if len(token) > 2 and token not in _STOPWORDS]
    return set(tokens)


def _is_redundant(a: str, b: str, threshold: float = 0.62) -> bool:
    tokens_a = _token_set(a)
    tokens_b = _token_set(b)
    if not tokens_a or not tokens_b:
        return False
    overlap = len(tokens_a & tokens_b) / max(1, min(len(tokens_a), len(tokens_b)))
    return overlap >= threshold


def _to_plain_language(text: str) -> str:
    if not text:
        return ""

    simplified = str(text)
    replacements = {
        "fundamentação": "explicação",
        "fundamento": "base",
        "contencioso": "discussão judicial",
        "exigibilidade": "cobrança",
        "jurisprudencial": "dos tribunais",
        "normativo": "da lei",
        "prescrição": "prazo legal vencido",
        "decadência": "perda de prazo",
        "ônus": "responsabilidade",
        "inadimplemento": "falta de pagamento/cumprimento",
        "rescisão": "encerramento",
        "vício processual": "problema no processo",
        "parte autora": "quem entrou com o pedido",
        "parte ré": "quem está sendo cobrado/processado",
    }

    for source, target in replacements.items():
        simplified = re.sub(rf"\b{re.escape(source)}\b", target, simplified, flags=re.IGNORECASE)

    simplified = re.sub(r"\s+", " ", simplified).strip()
    return simplified


def _build_plain_simplified_explanation(structured_json: dict, risks: list, fallback_explanation: str) -> str:
    compact = build_compact_context(structured_json)
    document_type = compact.get("document_type") or "documento jurídico"
    legal_refs_count = len(compact.get("legal_refs", []) or [])
    dates_count = len(compact.get("dates", []) or [])

    first_risk = _to_plain_language(risks[0]) if risks else "Há pontos que precisam de revisão antes de qualquer decisão."

    fallback_lines = [
        _to_plain_language(line.strip(" -"))
        for line in _normalize_multiline_text(fallback_explanation, max_chars=1200).splitlines()
        if line.strip()
    ]
    action_hint = fallback_lines[0] if fallback_lines else "Confira o documento completo com atenção em prazos, valores e pedidos."

    context_line = (
        f"- Em linguagem simples: o texto parece um(a) {document_type} e traz {legal_refs_count} referência(s) legal(is) e {dates_count} data(s) para conferência."
    )

    generated = [
        context_line,
        f"- Principal ponto de atenção: {first_risk}",
        f"- Próximo passo prático: {action_hint}",
    ]
    return "\n".join(generated)


def _normalize_risks(risks: list, summary: str, fallback_risks: list) -> List[str]:
    candidates = [str(risk or "").strip() for risk in (risks or []) if str(risk or "").strip()]
    fallback = [str(risk or "").strip() for risk in (fallback_risks or []) if str(risk or "").strip()]

    selected: List[str] = []
    for candidate in candidates + fallback:
        if not candidate:
            continue
        if _is_redundant(candidate, summary, threshold=0.72):
            continue
        if any(_is_redundant(candidate, existing, threshold=0.75) for existing in selected):
            continue
        selected.append(candidate)
        if len(selected) >= 3:
            break

    if not selected:
        selected = fallback[:3] if fallback else ["Risco não identificado com segurança; recomenda-se revisão jurídica humana."]

    return selected[:3]


def _normalize_simplified_explanation(
    summary: str,
    risks: list,
    simplified: str,
    fallback_explanation: str,
    structured_json: dict,
) -> str:
    clean_simplified = _normalize_multiline_text(simplified, max_chars=1800)
    lines = [line.strip(" -") for line in clean_simplified.splitlines() if line.strip()]
    has_topics = len(lines) >= 3

    if has_topics and not _is_redundant(clean_simplified, summary, threshold=0.68):
        normalized = "\n".join(f"- {line}" if not line.startswith("-") else line for line in lines[:3])
        if not _is_redundant(normalized, summary, threshold=0.68):
            return normalized

    return _build_plain_simplified_explanation(
        structured_json=structured_json,
        risks=risks,
        fallback_explanation=fallback_explanation,
    )


def _ensure_technical_summary(summary: str, structured_json: dict) -> str:
    normalized = _normalize_multiline_text(summary, max_chars=3800)
    lowered = normalized.lower()
    colloquial_markers = {
        "em termos simples",
        "em linguagem simples",
        "de forma simples",
        "em palavras simples",
    }

    if normalized and not any(marker in lowered for marker in colloquial_markers):
        return normalized

    compact = build_compact_context(structured_json)
    doc_type = compact.get("document_type", "indefinido")
    refs = compact.get("legal_refs", [])
    parties = compact.get("parties", [])
    dates = compact.get("dates", [])
    snippets = compact.get("relevant_snippets", [])

    foundation = refs[0] if refs else "fundamentação legal explícita não identificada"
    party_info = _top_items(parties, limit=2)
    temporal_info = _top_items(dates, limit=2)
    snippet = snippets[0][:200] if snippets else "trecho decisório não destacado automaticamente"

    return (
        f"Síntese técnico-jurídica: trata-se de {doc_type}, com partes relevantes ({party_info}) e marcos temporais ({temporal_info}). "
        f"A base normativa predominante indica {foundation}. "
        f"Trecho nuclear para validação: \"{snippet}\"."
    )


def _reduce_output_redundancy(result: dict, structured_json: dict) -> dict:
    local_result = analyze_locally(structured_json)

    summary = _normalize_multiline_text(result.get("summary", ""), max_chars=3800)
    if not summary:
        summary = _normalize_multiline_text(local_result.get("summary", ""), max_chars=3800)
    summary = _ensure_technical_summary(summary, structured_json)

    risks = _normalize_risks(
        risks=result.get("risks", []),
        summary=summary,
        fallback_risks=local_result.get("risks", []),
    )

    simplified = _normalize_simplified_explanation(
        summary=summary,
        risks=risks,
        simplified=str(result.get("simplified_explanation", "") or ""),
        fallback_explanation=str(local_result.get("simplified_explanation", "") or ""),
        structured_json=structured_json,
    )

    if _is_redundant(summary, simplified, threshold=0.63):
        simplified = _build_plain_simplified_explanation(
            structured_json=structured_json,
            risks=risks,
            fallback_explanation=str(local_result.get("simplified_explanation", "") or ""),
        )

    return {
        "summary": summary,
        "risks": risks,
        "simplified_explanation": simplified,
    }


def _normalize_text(value: str, max_chars: int = 180) -> str:
    cleaned = str(value or "").replace("\x00", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:max_chars]


def _normalize_multiline_text(value: str, max_chars: int = 1200) -> str:
    cleaned = str(value or "").replace("\x00", " ").replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"\s+", " ", line).strip() for line in cleaned.split("\n")]
    lines = [line for line in lines if line]
    normalized = "\n".join(lines).strip()
    return normalized[:max_chars]


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


def _assess_document_type_risks(doc_type: str, legal_refs: list, parties: list, cleaned_text: str) -> List[str]:
    """Analisa riscos específicos por tipo de documento."""
    risks = []
    lowered_text = cleaned_text.lower()
    
    if doc_type == "indefinido":
        risks.append("Tipo documental indefinido: exige validação manual da natureza jurídica do documento.")
    elif doc_type in ("acordao", "acórdão", "ag.reg", "agravo"):
        if not legal_refs:
            risks.append("Acórdão/Agravo sem referência legal clara: fundamento jurídico pode estar comprometido.")
        if "voto vencido" in lowered_text or "voto divergente" in lowered_text:
            risks.append("Há voto vencido/divergente: decisão pode estar polarizada; revisar fundamentação da maioria.")
    elif doc_type in ("petição", "petição inicial", "petição recursal"):
        if not parties or len(parties) < 2:
            risks.append("Petição com partes indefinidas: risco de vício processual ou incompetência.")
        if "pedido" not in lowered_text:
            risks.append("Petição sem pedido explícito: exigibilidade jurídica questionável.")
    elif doc_type == "despacho" and not legal_refs:
        risks.append("Despacho sem fundamentação legal: pode ser nulo ou passível de contencioso.")
    
    return risks


def _assess_legal_foundation_risks(legal_refs: list, dates: list, cleaned_text: str) -> List[str]:
    """Detecta riscos de fundamentação legal e temporal."""
    risks = []
    lowered_text = cleaned_text.lower()
    
    if not legal_refs and not dates:
        risks.append("Documento sem referência legal ou marco temporal: impossível validar legalidade ou prescrição.")
    elif not legal_refs:
        risks.append("Ausência de fundamentação legal explícita: argumento pode soçobrar em contencioso.")
    
    # Prescrição e decadência
    if any(token in lowered_text for token in ["prescri", "decad", "prazo prescricional", "decadência", "prescrito"]):
        risks.append("Menção a prescrição/decadência: revisar marcos temporais com rigor para evitar perda de direito.")
    
    # Temporal gap (muitas datas antigas vs. recentes)
    if dates and len(dates) >= 2:
        try:
            date_strs = [d.replace(".", "") for d in dates[:5]]
            date_values = [int(d.split()[-1]) if d else 0 for d in date_strs if d]
            if date_values and max(date_values) - min(date_values) > 10:
                risks.append("Grande intervalo temporal entre eventos: possível risco de lapso processual ou abandono.")
        except (ValueError, IndexError):
            pass
    
    return risks


def _assess_financial_risks(monetary_values: list, parties: list, cleaned_text: str) -> List[str]:
    """Detecta riscos relacionados a valores e obrigações financeiras."""
    risks = []
    lowered_text = cleaned_text.lower()
    
    financial_keywords = ["valor", "pagamento", "indeniza", "multa", "honorário", "custas", "taxa", "juros", "correção"]
    has_financial_mention = any(kw in lowered_text for kw in financial_keywords)
    
    if has_financial_mention and not monetary_values:
        risks.append("Há menção financeira (multa, pagamento, indenização) mas sem valores claros: risco de execução deficiente.")
    elif monetary_values and len(monetary_values) >= 1:
        if any(kw in lowered_text for kw in ["juros", "correção monetária", "índice"]) and len(monetary_values) == 1:
            risks.append("Valor principal sem incidências de juros/correção monetária explícita: cálculo final pode estar incompleto.")
    
    if has_financial_mention and not parties:
        risks.append("Questão financeira sem partes claramente identificadas: impossível executar condenatória.")
    
    return risks


def _assess_procedural_risks(cleaned_text: str) -> List[str]:
    """Detecta riscos procedimentais e vícios processuais."""
    risks = []
    lowered_text = cleaned_text.lower()
    
    # Urgência processual
    if any(token in lowered_text for token in ["liminar", "tutela de urgência", "urgência", "inaudita altera parte", "medida cautelar"]):
        risks.append("Há medida urgente/liminar: confirmar se cumpridos pressupostos (periculum, fumaça de bom direito, quinzenário).")
    
    # Inadimplemento e rescisão
    if any(token in lowered_text for token in ["rescindível", "rescisão", "inadimpl", "mora", "descumprimento", "cláusula penal"]):
        risks.append("Sinais de inadimplemento/rescisão: verificar impacto contratual, causalidade e prova de dano.")
    
    # Recurso
    if any(token in lowered_text for token in ["recurso", "apelação", "embargos", "agravo", "extraordinário"]):
        if "prazo recursal" not in lowered_text and "dias" not in lowered_text:
            risks.append("Há menção a recurso: confirmar se respeita prazos (15 dias comum, 30 CPC art. 1029).")
    
    return risks


def _assess_extraction_quality_risks(snippets: list, document_type: str) -> List[str]:
    """Avalia qualidade de extração e robustez de análise."""
    risks = []
    
    if len(snippets) <= 1:
        risks.append("Extração com poucos trechos jurídicos relevantes: recomenda-se revisar OCR/texto original.")
    
    if document_type not in ("acordao", "acórdão", "petição", "petição inicial") and len(snippets) <= 2:
        risks.append("Documento pouco estruturado ou OCR deficiente: análise pode estar incompleta.")
    
    return risks


def analyze_locally(structured_json: dict) -> dict:
    compact = build_compact_context(structured_json)
    cleaned_text = structured_json.get("cleaned_text", "")
    lowered_text = cleaned_text.lower()

    risks: List[str] = []
    
    # Extrair dados
    document_type = compact.get("document_type", "indefinido")
    legal_refs = compact.get("legal_refs", [])
    dates = compact.get("dates", [])
    parties = compact.get("parties", [])
    monetary_values = compact.get("monetary_values", [])
    snippets = compact.get("relevant_snippets", [])
    
    # Aplicar análises especializadas
    risks.extend(_assess_document_type_risks(document_type, legal_refs, parties, cleaned_text))
    risks.extend(_assess_legal_foundation_risks(legal_refs, dates, cleaned_text))
    risks.extend(_assess_financial_risks(monetary_values, parties, cleaned_text))
    risks.extend(_assess_procedural_risks(cleaned_text))
    risks.extend(_assess_extraction_quality_risks(snippets, document_type))
    
    # Deduplicar riscos
    seen = set()
    unique_risks = []
    for risk in risks:
        risk_normalized = risk.lower()[:100]
        if risk_normalized not in seen:
            seen.add(risk_normalized)
            unique_risks.append(risk)
    risks = unique_risks[:8]

    if not risks:
        risks.append("Sem risco crítico evidente por regras locais; recomenda-se revisão humana para confirmação jurídica.")

    entities = compact.get("entities", {})

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


def build_enriched_context(structured_json: dict) -> dict:
    """Enriquece contexto combinando dados extraídos + análise heurística local."""
    compact = build_compact_context(structured_json)
    local_analysis = analyze_locally(structured_json)
    
    enriched = {
        "extracted_data": compact,
        "preliminary_heuristic_analysis": {
            "summary": local_analysis.get("summary", ""),
            "identified_risks": local_analysis.get("risks", [])[:5],
            "suggested_actions": _extract_actions_from_explanation(local_analysis.get("simplified_explanation", "")),
        },
    }
    return enriched


def _extract_actions_from_explanation(explanation: str) -> list:
    """Extrai ações numeradas da explicação simplificada da análise local."""
    actions = []
    lines = explanation.split("\n")
    for line in lines:
        line = line.strip()
        if line and any(line.startswith(f"{i})") for i in range(1, 6)):
            action = re.sub(r"^\d+\)\s*", "", line)
            if action:
                actions.append(action[:120])
    return actions[:3]


def _build_prompt_with_enriched_context(structured_json: dict) -> str:
    """Monta o prompt incluindo dados extraídos E análise heurística para validação/refinamento."""
    enriched = build_enriched_context(structured_json)
    local_analysis_text = json.dumps(enriched["preliminary_heuristic_analysis"], ensure_ascii=False, separators=(",", ":"))
    contexto_estruturado = json.dumps(enriched["extracted_data"], ensure_ascii=False, separators=(",", ":"))
    
    return (
        "Você é um analista jurídico brasileiro especializado em acórdãos e peças processuais. "
        "Você receberá dados extraídos de um documento (por OCR/NLP) e uma análise heurística prévia. "
        "Sua tarefa é validar, expandir ou refinar essa análise de forma sucinta e objetiva, com linguagem clara.\n\n"
        "REGRAS OBRIGATÓRIAS:\n"
        "1) Não invente fatos; use apenas o contexto fornecido.\n"
        "2) Ignore ruídos de OCR, cabeçalhos repetidos e trechos truncados.\n"
        "3) Valide e refine a análise heurística fornecida; agregue riscos se necessário.\n"
        "4) Priorize: tema central, decisão, fundamento principal e riscos já identificados localmente.\n"
        "5) Seja conciso: frases curtas e diretas.\n"
        "6) Se discordar da análise local, justifique brevemente.\n"
        "7) Se faltar informação, explicite incerteza sem preencher lacunas com suposições.\n\n"
        "8) EVITE REDUNDÂNCIA ENTRE CAMPOS: summary, risks e simplified_explanation NÃO podem repetir o mesmo texto com sinônimos.\n"
        "9) Use papéis distintos: summary=fatos/decisão; risks=consequências práticas; simplified_explanation=orientação leiga em passos.\n"
        "10) O campo summary deve ser TÉCNICO-JURÍDICO, sucinto e coeso, com vocabulário jurídico objetivo (sem linguagem coloquial).\n\n"
        "ANÁLISE PRÉVIA (por heurísticas locais):\n"
        f"{local_analysis_text}\n\n"
        "RETORNE EXATAMENTE EM JSON VÁLIDO sem markdown no formato: "
        "{\"summary\":\"...\",\"risks\":[\"...\"],\"simplified_explanation\":\"...\"}. "
        "Sem limite de caracteres. "
        "Formato obrigatório: summary técnico-jurídico completo e coeso (4 a 8 linhas quando necessário); risks com EXATAMENTE 3 itens curtos e práticos; "
        "simplified_explanation em EXATAMENTE 3 tópicos para leigos, em uma única string com quebras de linha iniciadas por '- '.\n\n"
        "DADOS EXTRAÍDOS (estruturados):\n"
        f"{contexto_estruturado}"
    )


def build_prompt(structured_json: dict) -> str:
    return _build_prompt_with_enriched_context(structured_json)


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
        "Sem texto fora do JSON. "
        "Sem limite de caracteres. "
        "summary técnico-jurídico completo e coeso (4 a 8 linhas quando necessário); risks com EXATAMENTE 3 itens; "
        "simplified_explanation com EXATAMENTE 3 tópicos em uma única string usando '\\n- '.\n"
        "summary deve ser técnico-jurídico, sucinto e coeso (foco em tese, fundamento e decisão).\n"
        "Não repita as mesmas ideias entre campos: cada campo deve ter função diferente.\n"
        "Não invente fatos e ignore ruído de OCR.\n"
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


def _analyze_with_openai(structured_json: dict, prompt: str | None = None, max_output_tokens: int = 1400) -> str:
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
        "Com base no contexto, escreva um resumo jurídico TÉCNICO em PT-BR completo e coeso, de 4 a 8 linhas quando necessário, em texto puro. "
        "Foque em tese, fundamento normativo/jurisprudencial e decisão, sem listar riscos. "
        "Use linguagem técnico-jurídica objetiva e coesa, sem coloquialismos. "
        "Não invente fatos e ignore ruído de OCR. "
        f"Contexto: {context}"
    )
    risks_prompt = (
        "Com base no contexto, retorne SOMENTE um JSON array com EXATAMENTE 3 riscos jurídicos curtos e práticos em PT-BR, "
        "focados em consequências e impacto, sem repetir o resumo. "
        "sem texto extra. "
        f"Contexto: {context}"
    )
    simplified_prompt = (
        "Com base no contexto, escreva explicação simples para leigos em PT-BR com EXATAMENTE 3 tópicos, "
        "com orientação prática e linguagem não técnica, sem repetir frases do resumo ou dos riscos. "
        "em uma única string com quebra de linha e prefixo '- ' em cada tópico. "
        "Não invente fatos e ignore ruído de OCR. "
        f"Contexto: {context}"
    )

    summary_text = _analyze_with_gemini(structured_json, prompt=summary_prompt, max_output_tokens=900)
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

    summary = _normalize_multiline_text(summary_text, max_chars=1600)
    simplified = _normalize_multiline_text(simplified_text, max_chars=1800)

    if len(summary) < 35:
        summary = _normalize_multiline_text(f"{summary}\n{local_result['summary']}", max_chars=1600)
    if len(simplified) < 35:
        simplified = _normalize_multiline_text(f"{simplified}\n{local_result['simplified_explanation']}", max_chars=1800)

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
    if len(summary) < 35:
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

    result = _reduce_output_redundancy(_parse_llm_content(content, structured_json), structured_json)
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

        retry_result = _reduce_output_redundancy(_parse_llm_content(retry_content, structured_json), structured_json)
        if provider == "gemini" and _is_partial_result(retry_result):
            logger.info("Retry ainda parcial no Gemini; tentando geração segmentada.")
            return _reduce_output_redundancy(_analyze_with_gemini_segmented(structured_json), structured_json)
        return retry_result
    except Exception as exc:
        logger.warning("Falha no retry de resposta parcial (%s): %s", type(exc).__name__, exc)
        return result
