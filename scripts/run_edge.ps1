param(
  [string]$InputFile,
  [switch]$Offline,
  [switch]$SyncPending,
  [switch]$RecreateVenv
)

if (-not $InputFile -and -not $SyncPending) {
  Write-Error "Informe -InputFile com o caminho do documento."
  exit 1
}

Set-Location "$PSScriptRoot\..\edge"
$venvPython = ".\.venv\Scripts\python.exe"

if ($RecreateVenv -and (Test-Path ".\.venv")) {
  Remove-Item ".\.venv" -Recurse -Force
}

if (Test-Path $venvPython) {
  & $venvPython -c "import numpy" 2>$null
  if ($LASTEXITCODE -ne 0) {
    Remove-Item ".\.venv" -Recurse -Force
  }
}

if (-not (Test-Path $venvPython)) {
  python -m venv .venv
}

$venvPython = ".\.venv\Scripts\python.exe"
& $venvPython -m pip install --upgrade pip setuptools wheel
& $venvPython -m pip install -r requirements.txt

$tesseractCandidates = @(
  "C:\Program Files\Tesseract-OCR\tesseract.exe",
  "C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"
)

foreach ($candidate in $tesseractCandidates) {
  if (Test-Path $candidate) {
    $env:TESSERACT_CMD = $candidate
    break
  }
}

& $venvPython -c "import importlib.util; import sys; sys.exit(0 if importlib.util.find_spec('pt_core_news_sm') else 1)"
if ($LASTEXITCODE -ne 0) {
  & $venvPython -m spacy download pt_core_news_sm
}

$offlineFlag = ""
if ($Offline) {
  $offlineFlag = "--offline"
}

if ($SyncPending) {
  & $venvPython main.py --sync-pending
} else {
  if ($Offline) {
    & $venvPython main.py --input "$InputFile" --out "../data/structured_output.json" --offline
  } else {
    & $venvPython main.py --input "$InputFile" --out "../data/structured_output.json"
  }
}
