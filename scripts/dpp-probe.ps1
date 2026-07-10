param(
    [string] $Token = $env:DISCORD_BOT_TOKEN,
    [switch] $Start,
    [int] $TimeoutSeconds = 10
)

$ErrorActionPreference = "Stop"

if (-not $Token) {
    throw "DISCORD_BOT_TOKEN is not set. Pass -Token or set `$env:DISCORD_BOT_TOKEN."
}

powershell -ExecutionPolicy Bypass -File .\scripts\build-native.ps1

$Probe = ".\build\release-dpp-vs\native\directioner_native\directioner_dpp_probe.exe"
if (-not (Test-Path $Probe)) {
    throw "Missing DPP probe executable: $Probe"
}

$env:DISCORD_BOT_TOKEN = $Token
$env:PATH = "C:\vcpkg\installed\x64-windows\bin;" + $env:PATH
if ($Start) {
    & $Probe --start --timeout $TimeoutSeconds
} else {
    & $Probe
}
if ($LASTEXITCODE -ne 0) {
    throw "DPP probe exited with code $LASTEXITCODE."
}
