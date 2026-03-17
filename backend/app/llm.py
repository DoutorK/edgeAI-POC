import json

from openai import OpenAI

from .config import settings


def build_prompt(structured_json: dict) -> str:
    return (
        "Você é um assistente jurídico para análise preliminar de documentos. "
        "Retorne JSON com as chaves: summary, risks (lista), simplified_explanation. "
        "Evite aconselhamento definitivo e destaque incertezas.\n\n"
        f"Documento estruturado:\n{json.dumps(structured_json, ensure_ascii=False, indent=2)}"
    )


def analyze_with_llm(structured_json: dict) -> dict:
    if not settings.openai_api_key:
        return {
            "summary": "LLM indisponível: defina OPENAI_API_KEY para análise completa.",
            "risks": ["Análise jurídica avançada indisponível no modo offline/cloud desativado."],
            "simplified_explanation": "Foi feita apenas a extração local. Conecte o backend à API de LLM para interpretação avançada.",
        }

    client = OpenAI(api_key=settings.openai_api_key)
    response = client.responses.create(
        model=settings.llm_model,
        input=build_prompt(structured_json),
        temperature=0.2,
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
        return {
            "summary": content[:1200],
            "risks": ["Resposta do LLM em formato não estruturado; revisar prompt."],
            "simplified_explanation": "A resposta foi recebida, porém fora do formato JSON esperado.",
        }
