
# Minimal quick-start script to run the Discord bot
param(
    [string] $Token,
    [string] $Python = ".\.venv\Scripts\python.exe",
    [int] $TimeoutSeconds = 0
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Join-Path $ScriptDir ".."
Set-Location $ProjectRoot

# Just run the Discord bot with no pre-checks
$Args = @()
if ($Token) { $Args += @("-Token", $Token) }
if ($TimeoutSeconds -gt 0) { $Args += @("-TimeoutSeconds", $TimeoutSeconds) }

powershell -ExecutionPolicy Bypass -File $ScriptDir\run-discord.ps1 @Args
