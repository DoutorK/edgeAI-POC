const output = document.getElementById('output');
const processDocBtn = document.getElementById('processDocBtn');
const clearCacheBtn = document.getElementById('clearCacheBtn');
const docFile = document.getElementById('docFile');
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

  output.textContent = JSON.stringify(result, null, 2);
  statusEl.textContent = result.cache_hit ? 'Concluído (cache backend).' : 'Concluído.';
}

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

clearCacheBtn.addEventListener('click', async () => {
  const confirmed = window.confirm('Deseja limpar o cache do banco de dados? Esta ação é para testes.');
  if (!confirmed) return;

  statusEl.textContent = 'Limpando cache do backend...';

  try {
    const response = await fetch('http://localhost:8000/api/cache/clear', {
      method: 'POST',
    });

    if (!response.ok) {
      const body = await response.text();
      throw new Error(body || 'Falha ao limpar cache');
    }

    const result = await response.json();
    output.textContent = JSON.stringify(result, null, 2);
    statusEl.textContent = `Cache limpo. Registros removidos: ${result.deleted ?? 0}.`;
  } catch (error) {
    output.textContent = `Erro: ${error.message}`;
    statusEl.textContent = 'Erro ao limpar cache do backend.';
  }
});
