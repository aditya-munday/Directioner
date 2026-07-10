param(
    [string] $Python = ".\.venv\Scripts\python.exe"
)

$ErrorActionPreference = "Stop"
$env:PYTHONPATH = "src"
& $Python -m pytest tests
if ($LASTEXITCODE -ne 0) {
    throw "Tests failed."
}

