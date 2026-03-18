# Arquitetura híbrida (Edge + Cloud)

## Edge (Python)
- OCR com Tesseract (`edge/app/ocr.py`)
- Limpeza de texto (`edge/app/text_cleaner.py`)
- Extração estruturada por regex (`edge/app/extractors.py`)
- Classificação simples por palavras-chave (`edge/app/classifier.py`)
- Geração de JSON estruturado e envio ao backend (`edge/app/pipeline.py`)

## Cloud (FastAPI)
- Endpoint `/api/analyze` para receber JSON do edge
- Cache de análise por hash do texto
- Persistência em banco relacional (PostgreSQL via SQLAlchemy)
- Upload de JSON estruturado em S3
- Chamada de LLM para resumo, riscos e explicação simplificada

## Interface (Web simples)
- Entrada de JSON estruturado
- Chamada da API de análise
- Exibição de resposta consolidada

## Fluxo de dados
1. Usuário envia PDF/imagem no edge
2. Edge executa OCR + limpeza + extração local
3. Edge gera JSON estruturado (funciona offline)
4. Se online, edge envia JSON para backend
5. Backend usa LLM e retorna resumo, riscos e explicação simplificada
