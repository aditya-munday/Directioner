"""Async supervisor for the standalone DPP runtime process."""

from __future__ import annotations

import asyncio
import base64
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from directioner.config.settings import DiscordSettings
from directioner.discord.dpp_runtime import NativeDiscordTextEvent


EVENT_PREFIX = "DIRECTIONER_EVENT\t"


@dataclass(frozen=True, slots=True)
class StandaloneDppOptions:
    runtime_path: Path
    timeout_seconds: float = 0.0


def encode_protocol_text(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def decode_protocol_text(value: str) -> str:
    return base64.b64decode(value.encode("ascii"), validate=True).decode("utf-8")


def parse_runtime_event(line: str) -> NativeDiscordTextEvent | None:
    if not line.startswith(EVENT_PREFIX):
        return None

    parts = line.rstrip("\r\n").split("\t")
    if len(parts) != 8 or parts[1] != "TEXT_MESSAGE":
        raise ValueError(f"Unknown DPP runtime event line: {line!r}")

    return NativeDiscordTextEvent(
        guild_id=int(parts[2]),
        channel_id=int(parts[3]),
        message_id=int(parts[4]),
        author_id=int(parts[5]),
        author_is_bot=parts[6] == "1",
        content=decode_protocol_text(parts[7]),
    )


class StandaloneDppProcess:
    """Runs the DPP executable as a child process and exposes event-pump methods."""

    def __init__(
        self,
        settings: DiscordSettings,
        options: StandaloneDppOptions,
    ) -> None:
        self._settings = settings
        self._options = options
        self._process: asyncio.subprocess.Process | None = None
        self._stdout_task: asyncio.Task[None] | None = None
        self._events: asyncio.Queue[NativeDiscordTextEvent] = asyncio.Queue()

    async def start(self) -> None:
        if not self._settings.bot_token:
            raise RuntimeError("DISCORD_BOT_TOKEN is required to start the standalone DPP runtime")
        if not self._options.runtime_path.exists():
            raise RuntimeError(f"Missing standalone DPP runtime: {self._options.runtime_path}")

        env = os.environ.copy()
        env["DISCORD_BOT_TOKEN"] = self._settings.bot_token
        env["PATH"] = f"C:\\vcpkg\\installed\\x64-windows\\bin;{env.get('PATH', '')}"

        args = [str(self._options.runtime_path)]
        if self._options.timeout_seconds > 0:
            args.extend(["--timeout", str(int(self._options.timeout_seconds))])
        if self._settings.use_etf:
            args.append("--use-etf")
        if self._settings.compressed:
            args.append("--compressed")
        if self._settings.register_global_commands:
            args.append("--register-commands")
        args.extend(["--pool-threads", str(self._settings.native_pool_threads)])

        self._process = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=None,
            env=env,
        )
        self._stdout_task = asyncio.create_task(self._read_stdout())

    async def stop(self) -> None:
        process = self._process
        if process is None:
            return

        if process.stdin is not None and process.returncode is None:
            process.stdin.write(b"STOP\n")
            await process.stdin.drain()
            process.stdin.close()

        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except TimeoutError:
            process.terminate()
            await process.wait()

        if self._stdout_task is not None:
            await self._stdout_task

    def running(self) -> bool:
        return self._process is not None and self._process.returncode is None

    def poll_text_event(self) -> NativeDiscordTextEvent | None:
        try:
            return self._events.get_nowait()
        except asyncio.QueueEmpty:
            return None

    def poll_voice_frame(self) -> None:
        return None

    async def send_text_message(self, channel_id: int, content: str) -> bool:
        process = self._process
        if process is None or process.stdin is None or process.returncode is not None:
            return False
        line = f"SEND_TEXT\t{channel_id}\t{encode_protocol_text(content)}\n"
        process.stdin.write(line.encode("ascii"))
        await process.stdin.drain()
        return True

    async def _read_stdout(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            return

        while True:
            raw = await process.stdout.readline()
            if not raw:
                break
            line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
            try:
                event = parse_runtime_event(line)
            except Exception as exc:
                print(f"Failed to parse DPP runtime event: {exc}", file=sys.stderr, flush=True)
                continue
            if event is None:
                print(line, flush=True)
                continue
            await self._events.put(event)


class StandaloneDppChatSender:
    def __init__(
        self,
        process: StandaloneDppProcess,
        max_message_chars: int = 1900,
        cooldown_seconds: float = 1.2,
    ) -> None:
        self._process = process
        self._max_message_chars = max_message_chars
        self._cooldown = cooldown_seconds
        self._send_lock = asyncio.Lock()
        self._last_send_monotonic = 0.0
        from directioner.discord.chat_formatter import ChatOutputFormatter
        self._formatter = ChatOutputFormatter()

    async def send(
        self,
        channel_id: int,
        content: str,
        reply_to_message_id: str | None = None,
    ) -> None:
        messages = self._formatter.format(content, reply_to_message_id=reply_to_message_id)
        if not messages:
            return
        async with self._send_lock:
            for msg in messages:
                elapsed = asyncio.get_running_loop().time() - self._last_send_monotonic
                if elapsed < self._cooldown:
                    await asyncio.sleep(self._cooldown - elapsed)
                text = msg.content[: self._max_message_chars]
                await self._process.send_text_message(channel_id, text)
                self._last_send_monotonic = asyncio.get_running_loop().time()

    async def send_typing(self, channel_id: int) -> None:
        """Send typing indicator — best-effort via IPC command."""
        try:
            process = self._process._process
            if process and process.stdin and process.returncode is None:
                line = f"SEND_TYPING\t{channel_id}\n"
                process.stdin.write(line.encode("ascii"))
                await process.stdin.drain()
        except Exception:
            pass
