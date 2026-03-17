param(
  [Parameter(Mandatory = $true)]
  [string]$InputFile,
  [switch]$Offline,
  [switch]$RecreateVenv
)

$ErrorActionPreference = "Stop"

Set-Location "$PSScriptRoot\.."

if (-not (Test-Path $InputFile)) {
  Write-Error "Arquivo de entrada não encontrado: $InputFile"
  exit 1
}

Write-Host "[1/4] Subindo infraestrutura (PostgreSQL + MinIO)..."
docker compose up -d

if (-not $Offline) {
  Write-Host "[2/4] Iniciando backend em nova janela..."
  Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$PWD'; .\scripts\run_backend.ps1"

  Write-Host "Aguardando backend inicializar..."
  Start-Sleep -Seconds 8
}

Write-Host "[3/4] Executando pipeline edge..."
if ($Offline) {
  if ($RecreateVenv) {
    .\scripts\run_edge.ps1 -InputFile $InputFile -Offline -RecreateVenv
  } else {
    .\scripts\run_edge.ps1 -InputFile $InputFile -Offline
  }
} else {
  if ($RecreateVenv) {
    .\scripts\run_edge.ps1 -InputFile $InputFile -RecreateVenv
  } else {
    .\scripts\run_edge.ps1 -InputFile $InputFile
  }
}

Write-Host "[4/4] Concluído. Resultado estruturado em data/structured_output.json"
