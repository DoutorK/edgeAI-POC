# EdgeAI Legal PoC (Híbrido: Edge + Cloud)

Prova de Conceito para análise de documentos jurídicos com foco em **execução local** no edge e **análise semântica avançada** na nuvem.

## 🎯 Objetivo

Pipeline capaz de:
1. Receber documentos jurídicos (PDF/imagem)
2. Processar localmente no edge:
	 - OCR
	 - Limpeza de texto
	 - Extração estruturada
3. Enviar JSON estruturado para backend
4. Usar LLM na nuvem para:
	 - Resumo jurídico
	 - Identificação de riscos
	 - Explicação em linguagem simples

## ✅ Restrições atendidas

- Prioridade para execução local
- Sem LLM no dispositivo embarcado
- Modelos locais leves (regex + classificador simples + opção spaCy small)
- PoC sem complexidade desnecessária
- Modo parcialmente offline (`edge --offline`)

## 🏗️ Estrutura do projeto

> Estrutura resumida (alguns arquivos auxiliares foram omitidos para manter foco na visão geral).

```
edgeAI-POC/
├─ edge/
│  ├─ app/
│  │  ├─ ocr.py
│  │  ├─ text_cleaner.py
│  │  ├─ extractors.py
│  │  ├─ classifier.py
│  │  └─ pipeline.py
│  ├─ requirements.txt
│  └─ main.py
├─ backend/
│  ├─ app/
│  │  ├─ main.py
│  │  ├─ llm.py
│  │  ├─ storage.py
│  │  ├─ models.py
│  │  └─ database.py
│  └─ requirements.txt
├─ interface/
│  ├─ index.html
│  ├─ app.js
│  └─ styles.css
├─ scripts/
│  ├─ run_poc.ps1
│  ├─ run_edge.ps1
│  ├─ run_backend.ps1
│  └─ run_interface.ps1
├─ docs/
│  ├─ ARQUITETURA.md
│  └─ ETAPAS.md
├─ docker-compose.yml
└─ .env.example
```

## 🔄 Etapas de desenvolvimento

### Etapa 1 — MVP básico
- OCR de PDF/imagem no edge (`pytesseract`)
- Limpeza de texto
- Extração regex inicial

### Etapa 2 — Estruturação de dados
- Geração de JSON com:
	- Partes
	- Datas
	- Valores
	- Referências legais

### Etapa 3 — Inteligência embarcada
- Classificação simples de documento por palavras-chave
- NLP leve com spaCy small para entidades básicas (`people`, `organizations`, `locations`)
- Versionamento simples da extração (`extraction_version` no JSON)

### Etapa 4 — Integração com LLM
- Envio de JSON ao backend
- Prompt jurídico controlado
- Saídas:
	- Resumo
	- Riscos
	- Explicação simplificada

### Etapa 5 — Interface
- UI web mínima para envio/exibição de análise

## 🧰 Stack usada

### Edge
- Python
- Tesseract OCR
- OCR de PDF com `pdf2image` (Poppler) e fallback automático com `PyMuPDF`
- spaCy (modelo pequeno, opcional na PoC)
- ONNX Runtime (dependência preparada para inferência leve opcional)

### Cloud
- FastAPI
- OpenAI API (opcional; com fallback local por regras quando não configurada)
- PostgreSQL
- S3 (na PoC local: MinIO compatível S3)

## ⚙️ Setup rápido

### Execução com 1 comando (sem instalar dependências manualmente)
O script abaixo instala dependências automaticamente, sobe infra local e executa a pipeline:

```powershell
.\scripts\run_poc.ps1 -InputFile "C:\caminho\documento.pdf" -Offline
```

Modo híbrido (edge + backend + LLM):

```powershell
.\scripts\run_poc.ps1 -InputFile "C:\caminho\documento.pdf"
```

Para recriar virtualenv do edge quando ambiente estiver inconsistente:

```powershell
.\scripts\run_poc.ps1 -InputFile "C:\caminho\documento.pdf" -Offline -RecreateVenv
```

### 1) Infra local (PostgreSQL + S3 compatível)
```bash
docker compose up -d
```

### 2) Configurar variáveis
- Copie `.env.example` para `.env`
- Ajuste `OPENAI_API_KEY` (opcional para modo híbrido com LLM; sem chave, o backend usa análise local por regras)

### Pré-requisito OCR no Windows
- Instale o Tesseract OCR (ex.: `winget install UB-Mannheim.TesseractOCR`)
- Se necessário, configure `TESSERACT_CMD` no `.env`, por exemplo:
	- `TESSERACT_CMD=C:/Program Files/Tesseract-OCR/tesseract.exe`

### 3) Subir backend
No PowerShell:
```powershell
.\scripts\run_backend.ps1
```

### 4) Rodar pipeline edge (offline)
```powershell
.\scripts\run_edge.ps1 -InputFile "C:\caminho\documento.pdf" -Offline
```

### 5) Rodar pipeline edge (híbrido)
```powershell
.\scripts\run_edge.ps1 -InputFile "C:\caminho\documento.pdf"
```

### 5.1) Sincronizar pendências (fallback offline → online)
```powershell
.\scripts\run_edge.ps1 -SyncPending
```

### 6) Abrir interface web
```powershell
.\scripts\run_interface.ps1
```
Abra: `http://localhost:5173`

Na interface, você pode usar dois fluxos:
- **Fluxo direto**: selecionar PDF/imagem e clicar em **Processar documento completo**
- **Fluxo JSON**: carregar `data/structured_output.json` e clicar em **Analisar no backend (LLM)**

## 📦 Saídas esperadas

1. JSON estruturado (`data/structured_output.json`)
2. Resumo jurídico
3. Lista de possíveis riscos
4. Explicação simplificada para leigos

## 🔁 Fallback offline → online

- `--offline`: extrai e estrutura localmente sem backend
- Sem `--offline`: envia para backend, aplica LLM (ou fallback local por regras se não houver chave/API) e retorna análise
- Se backend/rede estiver indisponível, o payload vai para `data/pending_sync` (fila local)
- Use `-SyncPending` para reenviar pendências quando voltar online
- Backend possui cache por hash de conteúdo para evitar reprocessamento
- Edge possui cache local de respostas para reduzir latência e custo

## 🧪 Critérios de sucesso da PoC

- Processa documento real (PDF/imagem)
- Extrai dados relevantes localmente
- Gera análise coerente via LLM
- Mostra separação clara Edge x Cloud

## 💡 Recomendações para reduzir tamanho de LLM sem perder muita acurácia

Como a restrição é não rodar LLM no edge, estas técnicas valem para otimização de custos/latência na nuvem:

1. **Quantização pós-treinamento** (8-bit / 4-bit) para inferência mais barata.
2. **Distilação** para modelo menor especializado no domínio jurídico.
3. **RAG com chunking jurídico** para reduzir dependência de modelo grande.
4. **Prompt caching e cache semântico** para consultas recorrentes.
5. **Roteamento de modelos**: modelo pequeno por padrão e maior apenas em casos de baixa confiança.

## Próximas evoluções opcionais

- Extração de entidades com spaCy treinado/fine-tuned para jurídico em PT-BR
- Classificação com ONNX/TFLite (modelo embarcado leve)
- Integração Telegram como interface alternativa
- Versionamento de modelos e regras de extração