
# Runs all pre-flight checks (native smoke, tests, health check) then starts the Discord bot
param(
    [string] $Token,
    [string] $Python = ".\.venv\Scripts\python.exe",
    [switch] $UseEtf,
    [switch] $Compressed,
    [switch] $RegisterCommands,
    [int] $PoolThreads = 1,
    [int] $TimeoutSeconds = 0
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Join-Path $ScriptDir ".."
Set-Location $ProjectRoot
$env:PYTHONPATH = "src"

Write-Host "=== Step 1: Native Smoke Check ===" -ForegroundColor Cyan
powershell -ExecutionPolicy Bypass -File $ScriptDir\build-native.ps1
if ($LASTEXITCODE -ne 0) {
    throw "Build failed."
}
& $Python -m directioner.app native-smoke
if ($LASTEXITCODE -ne 0) {
    throw "Native smoke check failed."
}

Write-Host "`n=== Step 2: Run All Tests ===" -ForegroundColor Cyan
powershell -ExecutionPolicy Bypass -File $ScriptDir\test.ps1 -Python $Python
if ($LASTEXITCODE -ne 0) {
    throw "Tests failed."
}

Write-Host "`n=== Step 3: Health Check ===" -ForegroundColor Cyan
& $Python -m directioner.app health-check
if ($LASTEXITCODE -ne 0) {
    throw "Health check failed."
}

Write-Host "`n=== Step 4: Start Discord Bot ===" -ForegroundColor Cyan
$Args = @("-SmokeFirst")
if ($Token) { $Args += @("-Token", $Token) }
if ($UseEtf) { $Args += "-UseEtf" }
if ($Compressed) { $Args += "-Compressed" }
if ($RegisterCommands) { $Args += "-RegisterCommands" }
if ($PoolThreads -ne 1) { $Args += @("-PoolThreads", $PoolThreads) }
if ($TimeoutSeconds -gt 0) { $Args += @("-TimeoutSeconds", $TimeoutSeconds) }

powershell -ExecutionPolicy Bypass -File $ScriptDir\run-discord.ps1 @Args
