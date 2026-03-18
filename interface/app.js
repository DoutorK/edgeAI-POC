const output = document.getElementById('output');
const jsonInput = document.getElementById('jsonInput');
const analyzeBtn = document.getElementById('analyzeBtn');
const processDocBtn = document.getElementById('processDocBtn');
const docFile = document.getElementById('docFile');
const jsonFile = document.getElementById('jsonFile');
const summaryOutput = document.getElementById('summaryOutput');
const risksOutput = document.getElementById('risksOutput');
const simpleOutput = document.getElementById('simpleOutput');
const statusEl = document.getElementById('status');

function renderResult(result) {
  summaryOutput.textContent = result.summary || '-';
  simpleOutput.textContent = result.simplified_explanation || '-';

  risksOutput.innerHTML = '';
  const risks = result.risks || [];
  if (!risks.length) {
    const li = document.createElement('li');
    li.textContent = 'Nenhum risco identificado.';
    risksOutput.appendChild(li);
  } else {
    for (const risk of risks) {
      const li = document.createElement('li');
      li.textContent = risk;
      risksOutput.appendChild(li);
    }
  }

  if (result.structured_json) {
    jsonInput.value = JSON.stringify(result.structured_json, null, 2);
  }

  output.textContent = JSON.stringify(result, null, 2);
  statusEl.textContent = result.cache_hit ? 'Concluído (cache backend).' : 'Concluído.';
}

jsonFile.addEventListener('change', async (event) => {
  const [file] = event.target.files;
  if (!file) return;

  try {
    const content = await file.text();
    const parsed = JSON.parse(content);
    const structured = parsed.structured_data || parsed;
    jsonInput.value = JSON.stringify(structured, null, 2);
    statusEl.textContent = 'JSON carregado com sucesso.';
  } catch (error) {
    statusEl.textContent = 'Falha ao ler arquivo JSON.';
  }
});

analyzeBtn.addEventListener('click', async () => {
  output.textContent = 'Processando...';
  statusEl.textContent = 'Enviando para backend...';

  let payload;
  try {
    payload = JSON.parse(jsonInput.value);
  } catch (error) {
    output.textContent = 'JSON inválido. Verifique o conteúdo colado.';
    statusEl.textContent = 'JSON inválido.';
    return;
  }

  try {
    const response = await fetch('http://localhost:8000/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const body = await response.text();
      throw new Error(body || 'Falha na chamada da API');
    }

    const result = await response.json();
    renderResult(result);
  } catch (error) {
    output.textContent = `Erro: ${error.message}`;
    statusEl.textContent = 'Erro na integração com backend.';
  }
});

processDocBtn.addEventListener('click', async () => {
  const [file] = docFile.files;
  if (!file) {
    statusEl.textContent = 'Selecione um PDF/imagem antes de processar.';
    return;
  }

  output.textContent = 'Processando documento...';
  statusEl.textContent = 'Executando OCR + extração + análise...';

  try {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch('http://localhost:8000/api/process-file', {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const body = await response.text();
      throw new Error(body || 'Falha no processamento do documento');
    }

    const result = await response.json();
    renderResult(result);
  } catch (error) {
    output.textContent = `Erro: ${error.message}`;
    statusEl.textContent = 'Erro no processamento direto de documento.';
  }
});
