"""Built-in filesystem tools.

Provide sandboxed read-only filesystem access exposed as :class:`ToolSpec`
instances. Every path argument is resolved relative to a configured base
directory and access outside that directory is rejected so the tools cannot be
used to read arbitrary files on the host.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .registry import ToolSpec


class FilesystemToolError(ValueError):
    """Raised when a path is missing, invalid, or escapes the sandbox."""


_MAX_READ_BYTES = 64 * 1024


def _resolve_within(base: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative.strip():
        raise FilesystemToolError("A non-empty string 'path' argument is required")
    base_resolved = base.resolve()
    candidate = (base_resolved / relative).resolve()
    if candidate != base_resolved and base_resolved not in candidate.parents:
        raise FilesystemToolError(f"Path escapes the allowed directory: {relative!r}")
    return candidate


def read_file_tool(base_directory: str | Path) -> ToolSpec:
    """Return a tool that reads a UTF-8 text file inside ``base_directory``."""

    base = Path(base_directory)

    async def _handle(arguments: dict[str, Any]) -> dict[str, Any]:
        target = _resolve_within(base, arguments.get("path", ""))
        if not target.is_file():
            raise FilesystemToolError(f"File not found: {arguments.get('path')!r}")
        data = target.read_bytes()[:_MAX_READ_BYTES]
        text = data.decode("utf-8", errors="replace")
        return {
            "path": str(target),
            "content": text,
            "truncated": target.stat().st_size > _MAX_READ_BYTES,
        }

    return ToolSpec(
        name="read_file",
        description=(
            "Read a UTF-8 text file located inside the assistant's allowed "
            "directory. Accepts a 'path' relative to that directory."
        ),
        handler=_handle,
    )


def list_directory_tool(base_directory: str | Path) -> ToolSpec:
    """Return a tool that lists directory entries inside ``base_directory``."""

    base = Path(base_directory)

    async def _handle(arguments: dict[str, Any]) -> dict[str, Any]:
        relative = arguments.get("path", ".")
        target = _resolve_within(base, relative or ".")
        if not target.is_dir():
            raise FilesystemToolError(f"Directory not found: {relative!r}")
        entries = []
        for child in sorted(target.iterdir(), key=lambda item: item.name):
            entries.append(
                {
                    "name": child.name,
                    "kind": "directory" if child.is_dir() else "file",
                }
            )
        return {"path": str(target), "entries": entries}

    return ToolSpec(
        name="list_directory",
        description=(
            "List the files and directories inside the assistant's allowed "
            "directory. Accepts an optional 'path' relative to that directory."
        ),
        handler=_handle,
    )
