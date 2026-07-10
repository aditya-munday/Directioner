# Building Directioner

## Prerequisites

- Visual Studio C++ toolchain with the Windows SDK.
- CMake and Ninja.
- Python 3.12 or newer.
- vcpkg with DPP installed for `x64-windows`.
- A project virtual environment with `nanobind`, `PyYAML`, `pytest`, and `pytest-asyncio`.

The machine used for this scaffold has DPP available at:

```text
C:\vcpkg\installed\x64-windows\share\dpp\dppConfig.cmake
```

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install nanobind PyYAML pytest pytest-asyncio
```

## Build Native Extension

Release build with DPP:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build-native.ps1
```

Debug build with DPP:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build-native.ps1 -Debug
```

Build without DPP, useful for isolating nanobind/shared-memory issues:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build-native.ps1 -NoDpp
```

The build emits the extension into:

```text
src\directioner\_native.cp312-win_amd64.pyd
```

## Test

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test.ps1
```

## Native Smoke Check

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m directioner.app native-smoke
```

Expected output:

```text
Native extension: directioner native ABI 0.1.0 via nanobind
Shared-memory smoke: write=True stream_id=1 sequence=2 payload_bytes=4
```

## Run Discord

Use a fresh Discord bot token. If a token has ever been pasted into chat, logs, screenshots, or a repo, reset it in the Discord Developer Portal.

```powershell
$env:DISCORD_BOT_TOKEN = "..."
powershell -ExecutionPolicy Bypass -File .\scripts\run-discord.ps1 -SmokeFirst
```

The wrapper starts the Python bridge over the standalone native DPP executable by default. This keeps DPP outside the Python process while still routing Discord text events into Python orchestration.

The wrapper starts DPP in conservative mode by default:

- JSON websocket protocol, not ETF
- uncompressed gateway payloads
- one DPP pool thread
- no global slash-command registration

You can opt into features later:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-discord.ps1 -SmokeFirst -UseEtf -Compressed -RegisterCommands -PoolThreads 4
```

You can launch the raw standalone executable without Python orchestration for diagnosis:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-discord.ps1 -SmokeFirst -RawStandalone
```

The older embedded Python/nanobind DPP startup path is still available for debugging only:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-discord.ps1 -SmokeFirst -Embedded
```

At the time of writing, embedded DPP crashes during `dpp::cluster` construction on this machine. Use the standalone runtime unless that has been fixed.

## DPP Probe

Construction-only:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\dpp-probe.ps1 -Token "dummy-token"
```

Gateway start probe:

```powershell
$env:DISCORD_BOT_TOKEN = "..."
powershell -ExecutionPolicy Bypass -File .\scripts\dpp-probe.ps1 -Start -TimeoutSeconds 10
```

The runtime now prints startup checkpoints:

```text
Native extension: ...
Starting Python bridge over standalone DPP runtime: .\build\release-dpp-vs\native\directioner_native\directioner_dpp_runtime.exe
Starting standalone DPP Python bridge: build\release-dpp-vs\native\directioner_native\directioner_dpp_runtime.exe
Standalone DPP bridge started. Press Ctrl+C to stop.
Directioner standalone DPP runtime
DPP version: D++ 10.1.5 (21-Dec-2025)
Mode: compressed=false etf=false register_commands=false pool_threads=1
Starting DPP gateway...
DPP gateway start returned. Press Ctrl+C to stop.
```

## Runtime Notes

`directioner.native` registers common Windows DLL search paths before importing `_native`, including:

- `C:\vcpkg\installed\x64-windows\bin`
- `C:\vcpkg\installed\x64-windows\debug\bin`
- the active Python runtime directories

If DPP or other native DLLs live somewhere else, set:

```powershell
$env:DIRECTIONER_DLL_DIRS = "C:\path\to\dlls"
```
