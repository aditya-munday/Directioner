param(
    [string] $Token,
    [string] $Python = ".\.venv\Scripts\python.exe",
    [switch] $SmokeFirst,
    [switch] $UseEtf,
    [switch] $Compressed,
    [switch] $RegisterCommands,
    [int] $PoolThreads = 1,
    [int] $TimeoutSeconds = 0,
    [switch] $DppSmokeFirst,
    [switch] $Embedded,
    [switch] $RawStandalone
)

$ErrorActionPreference = "Stop"

$envFile = Join-Path $PSScriptRoot "..\.env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) {
            return
        }
        $eq = $line.IndexOf("=")
        if ($eq -lt 1) {
            return
        }
        $name = $line.Substring(0, $eq).Trim()
        $value = $line.Substring($eq + 1).Trim()
        if ($value.Length -ge 2 -and $value.StartsWith('"') -and $value.EndsWith('"')) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        Set-Item -Path "Env:$name" -Value $value
    }
}

if (-not $Token) {
    $Token = $env:DISCORD_BOT_TOKEN
}

$existing = Get-CimInstance Win32_Process -Filter "name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like '*directioner.app*run-discord*' }
if ($existing) {
    Write-Host "Stopping existing Directioner bridge process(es)..."
    $existing | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 2
}

if (-not (Test-Path $Python)) {
    throw "Missing Python virtualenv. Create it first with: python -m venv .venv"
}

if (-not $Token) {
    throw "DISCORD_BOT_TOKEN is not set. Pass -Token or set `$env:DISCORD_BOT_TOKEN."
}

$env:DISCORD_BOT_TOKEN = $Token
$env:PYTHONPATH = "src"
$env:DIRECTIONER_DPP_USE_ETF = if ($UseEtf) { "true" } else { "false" }
$env:DIRECTIONER_DPP_COMPRESSED = if ($Compressed) { "true" } else { "false" }
$env:DIRECTIONER_DPP_REGISTER_COMMANDS = if ($RegisterCommands) { "true" } else { "false" }
$env:DIRECTIONER_DPP_POOL_THREADS = "$PoolThreads"

if ($SmokeFirst) {
    & $Python -m directioner.app native-smoke
    if ($LASTEXITCODE -ne 0) {
        throw "Native smoke check failed."
    }
}

if ($DppSmokeFirst) {
    powershell -ExecutionPolicy Bypass -File .\scripts\dpp-probe.ps1 -Token $Token
    if ($LASTEXITCODE -ne 0) {
        throw "DPP construct smoke check failed."
    }
}

$Runtime = ".\build\release-dpp-vs\native\directioner_native\directioner_dpp_runtime.exe"
if (-not (Test-Path $Runtime)) {
    powershell -ExecutionPolicy Bypass -File .\scripts\build-native.ps1
}

if ($Embedded) {
    Write-Warning "Embedded DPP is diagnostic-only and currently crashes on this machine. Prefer the default standalone runtime."
    if ($TimeoutSeconds -gt 0) {
        & $Python -m directioner.app run-discord --timeout-seconds $TimeoutSeconds
    } else {
        & $Python -m directioner.app run-discord
    }
} elseif ($RawStandalone) {
    $env:PATH = "C:\vcpkg\installed\x64-windows\bin;" + $env:PATH
    Write-Host "Starting standalone DPP runtime: $Runtime"
    Write-Host "Mode: embedded=false compressed=$($Compressed.IsPresent) etf=$($UseEtf.IsPresent) register_commands=$($RegisterCommands.IsPresent) pool_threads=$PoolThreads"
    $Args = @()
    if ($TimeoutSeconds -gt 0) {
        $Args += @("--timeout", "$TimeoutSeconds")
    }
    if ($UseEtf) {
        $Args += "--use-etf"
    }
    if ($Compressed) {
        $Args += "--compressed"
    }
    if ($RegisterCommands) {
        $Args += "--register-commands"
    }
    $Args += @("--pool-threads", "$PoolThreads")
    & $Runtime @Args
} else {
    Write-Host "Starting Python bridge over standalone DPP runtime: $Runtime"
    $Args = @("run-discord-bridge", "--runtime", $Runtime)
    if ($TimeoutSeconds -gt 0) {
        $Args += @("--timeout-seconds", "$TimeoutSeconds")
    }
    & $Python -m directioner.app @Args
}
if ($LASTEXITCODE -ne 0) {
    throw "Discord runtime exited with code $LASTEXITCODE."
}
