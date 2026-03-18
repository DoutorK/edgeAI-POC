param(
	[switch]$RecreateVenv
)

$scriptBase = $PSScriptRoot
if (-not $scriptBase -or -not (Test-Path $scriptBase)) {
	$candidateFromCwd = Join-Path (Get-Location) "scripts"
	if (Test-Path $candidateFromCwd) {
		$scriptBase = $candidateFromCwd
	} elseif (Test-Path (Join-Path (Get-Location) "backend")) {
		$scriptBase = Get-Location
	} else {
		throw "Não foi possível determinar a pasta base do script. Execute .\scripts\run_backend.ps1 a partir da raiz do projeto."
	}
}

Set-Location (Join-Path $scriptBase "..\backend")
$venvPython = ".\.venv\Scripts\python.exe"

if ($RecreateVenv -and (Test-Path ".\.venv")) {
	Remove-Item ".\.venv" -Recurse -Force
}

if (-not (Test-Path $venvPython)) {
	python -m venv .venv
}

$venvPython = ".\.venv\Scripts\python.exe"
$requirementsHash = (Get-FileHash "requirements.txt" -Algorithm SHA256).Hash
$depsHashFile = ".\.venv\.deps.hash"
$installDeps = $true

if (Test-Path $depsHashFile) {
	$storedHash = (Get-Content $depsHashFile -Raw).Trim()
	if ($storedHash -eq $requirementsHash) {
		$installDeps = $false
	}
}

if ($installDeps) {
	& $venvPython -m pip install --upgrade pip setuptools wheel
	& $venvPython -m pip install -r requirements.txt
	Set-Content -Path $depsHashFile -Value $requirementsHash -Encoding utf8
}

& $venvPython -m uvicorn app.main:app --reload --port 8000
