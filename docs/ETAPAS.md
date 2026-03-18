# Etapas de desenvolvimento

## Etapa 1 — MVP básico
- [x] Upload local por CLI (`--input`)
- [x] OCR funcional para PDF/imagem
- [x] Extração simples com regex

## Etapa 2 — Estruturação de dados
- [x] Transformação para JSON estruturado
- [x] Campos: partes, datas, valores, referências legais

## Etapa 3 — Inteligência embarcada
- [x] Classificação simples de tipo documental
- [x] Enriquecimento com spaCy pequeno (entidades básicas)
- [x] Versionamento simples da extração local

## Etapa 4 — Integração com LLM
- [x] Envio de JSON estruturado ao backend
- [x] Prompt para análise jurídica preliminar
- [x] Saídas: resumo, riscos e explicação simplificada
- [x] Fallback com fila local de sincronização

## Etapa 5 — Interface
- [x] Interface web mínima
- [x] Upload/entrada de JSON estruturado
- [x] Exibição do resultado final
