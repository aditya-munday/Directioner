# Directioner Operations

## Service Runner

Recommended process model in production:

- Run `directioner run-discord-bridge` under a process supervisor.
- Restart on crash with exponential backoff.
- Persist logs to files and central log sink.
- Keep secrets in environment variables, not YAML files.

### Windows Task Scheduler / NSSM

Use NSSM or Task Scheduler to run:

```powershell
.\.venv\Scripts\python.exe -m directioner.app run-discord-bridge --runtime .\build\release-dpp-vs\native\directioner_native\directioner_dpp_runtime.exe
```

## GPU and Runtime Dependencies

Core runtime:

- Python 3.11+
- vcpkg DPP runtime dependencies for native extension and standalone DPP process
- Visual C++ Redistributable

Model runtime options:

- STT/TTS local GPU mode requires NVIDIA driver + CUDA stack matching model libraries.
- Sidecar/server mode requires network reachability and API credentials.

## Release Packaging

Suggested release artifact layout:

- `directioner/` Python package wheel
- `directioner_dpp_runtime.exe` standalone native process
- required native DLLs (`dpp`, `opus`, and vcpkg runtime DLLs)
- `configs/app.production.example.yaml` template

Build steps:

1. Build native release (`scripts/build-native.ps1`).
2. Run tests (`scripts/test.ps1`).
3. Build wheel via `python -m build` (or scikit-build pipeline).
4. Bundle wheel + native executable + DLLs into release zip.
