"""Safe access to the nanobind native extension."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import ModuleType

_native: ModuleType | None
_native_error: BaseException | None
_dll_directory_handles: list[object] = []


def _configure_windows_dll_search_path() -> None:
    if os.name != "nt" or not hasattr(os, "add_dll_directory"):
        return

    candidates: list[Path] = []

    env_dirs = os.getenv("DIRECTIONER_DLL_DIRS", "")
    candidates.extend(Path(item) for item in env_dirs.split(os.pathsep) if item)

    vcpkg_root = Path(os.getenv("VCPKG_ROOT", r"C:\vcpkg"))
    candidates.extend(
        [
            vcpkg_root / "installed" / "x64-windows" / "bin",
            vcpkg_root / "installed" / "x64-windows" / "debug" / "bin",
        ]
    )

    candidates.extend(
        [
            Path(sys.executable).parent,
            Path(sys.base_prefix),
            Path(sys.prefix),
        ]
    )

    for directory in candidates:
        if not directory.exists():
            continue
        try:
            _dll_directory_handles.append(os.add_dll_directory(str(directory)))
        except OSError:
            continue


try:
    _configure_windows_dll_search_path()
    from directioner import _native as _native

    _native_error = None
except BaseException as exc:  # pragma: no cover - depends on local native build
    _native = None
    _native_error = exc


def require_native() -> ModuleType:
    """Return the native extension or raise a helpful runtime error."""

    if _native is None:
        raise RuntimeError(
            "Directioner native extension is not available. "
            "Build the project with scikit-build-core/nanobind first."
        ) from _native_error
    return _native


def native_build_info() -> str:
    native = require_native()
    return str(native.native_build_info())
