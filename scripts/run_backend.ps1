Set-Location "$PSScriptRoot\..\backend"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
$venvPython = ".\.venv\Scripts\python.exe"
& $venvPython -m pip install --upgrade pip setuptools wheel
& $venvPython -m pip install -r requirements.txt
& $venvPython -m uvicorn app.main:app --reload --port 8000
