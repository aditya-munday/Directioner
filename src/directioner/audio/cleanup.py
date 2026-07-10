"""Shared-memory cleanup and unlink policy for stale ring objects."""

from __future__ import annotations

import logging

from directioner.audio.shared_memory import ChannelName, SharedMemoryBus

logger = logging.getLogger(__name__)


def cleanup_stale_rings(bus: SharedMemoryBus) -> dict[str, bool]:
    """Attempt to close and unlink all known shared-memory ring objects.

    Safe to call on startup to clear leftover mappings from a previous crash,
    and on shutdown to release OS resources.  Returns a dict of channel name
    to success flag.
    """
    results: dict[str, bool] = {}
    try:
        from directioner.native import require_native
        native = require_native()
    except Exception as exc:
        logger.debug("cleanup.native_unavailable err=%s", exc)
        return results

    for channel in ChannelName:
        name = bus.object_name(channel)
        try:
            native.SharedMemoryRegion.unlink(name)
            results[channel.value] = True
            logger.debug("cleanup.unlinked channel=%s name=%s", channel.value, name)
        except Exception as exc:
            results[channel.value] = False
            logger.debug("cleanup.unlink_skip channel=%s err=%s", channel.value, exc)

    return results


def cleanup_on_startup(bus: SharedMemoryBus) -> None:
    """Best-effort cleanup of stale rings before creating new ones."""
    results = cleanup_stale_rings(bus)
    cleaned = sum(1 for ok in results.values() if ok)
    if cleaned:
        logger.info("cleanup.startup_cleaned count=%d", cleaned)


def cleanup_on_shutdown(bus: SharedMemoryBus) -> None:
    """Best-effort cleanup of rings on graceful shutdown."""
    results = cleanup_stale_rings(bus)
    cleaned = sum(1 for ok in results.values() if ok)
    logger.info("cleanup.shutdown_cleaned count=%d", cleaned)
