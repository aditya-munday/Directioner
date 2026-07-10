"""Python control layer for the native DPP Discord runtime."""

from __future__ import annotations

from dataclasses import dataclass

from directioner.audio.shared_memory import ChannelName, SharedMemoryBus
from directioner.config.settings import DiscordSettings
from directioner.native import require_native


@dataclass(frozen=True, slots=True)
class NativeDiscordTextEvent:
    guild_id: int
    channel_id: int
    message_id: int
    author_id: int
    content: str
    author_is_bot: bool


@dataclass(frozen=True, slots=True)
class NativeDiscordVoiceFrame:
    user_id: int
    pcm_s16le_stereo_48khz: bytes


@dataclass(frozen=True, slots=True)
class NativeVoiceGatewayStats:
    """Statistics from the native DPP voice gateway."""

    text_messages_received: int
    voice_frames_received: int
    voice_bytes_received: int
    pcm_bytes_sent: int
    voice_ready_events: int
    reconnects: int
    errors: int


class DppDiscordRuntime:
    """Owns the native DPP bot object and presents a Python-friendly API."""

    def __init__(self, settings: DiscordSettings) -> None:
        self._settings = settings
        native = require_native()
        self._native = native
        self._runtime = native.DppDiscordRuntime()

    def construct_smoke(self) -> str:
        return str(self._native.dpp_construct_smoke(self._build_config()))

    def start(self) -> None:
        if not self._settings.bot_token:
            raise RuntimeError("DISCORD_BOT_TOKEN is required to start the DPP runtime")

        self._runtime.start(self._build_config())

    def _build_config(self) -> object:
        config = self._native.DiscordBotConfig()
        config.token = self._settings.bot_token
        config.shard_count = self._settings.shard_count
        config.cluster_id = self._settings.cluster_id
        config.cluster_count = self._settings.cluster_count
        config.pool_threads = self._settings.native_pool_threads
        config.compressed = self._settings.compressed
        config.use_etf = self._settings.use_etf
        config.register_global_commands = self._settings.register_global_commands
        return config

    def stop(self) -> None:
        self._runtime.stop()

    def running(self) -> bool:
        return bool(self._runtime.running())

    def stats(self) -> NativeVoiceGatewayStats | None:
        """Return native voice gateway statistics, or None if not available."""
        native_stats = self._runtime.stats()
        if native_stats is None:
            return None
        return NativeVoiceGatewayStats(
            text_messages_received=int(native_stats.text_messages_received),
            voice_frames_received=int(native_stats.voice_frames_received),
            voice_bytes_received=int(native_stats.voice_bytes_received),
            pcm_bytes_sent=int(native_stats.pcm_bytes_sent),
            voice_ready_events=int(native_stats.voice_ready_events),
            reconnects=int(native_stats.reconnects),
            errors=int(native_stats.errors),
        )

    def join_user_voice(self, guild_id: int, user_id: int) -> bool:
        return bool(self._runtime.join_user_voice(guild_id, user_id))

    def connect_voice(
        self,
        guild_id: int,
        channel_id: int,
        *,
        self_mute: bool = False,
        self_deaf: bool = False,
    ) -> bool:
        return bool(self._runtime.connect_voice(guild_id, channel_id, self_mute, self_deaf))

    def disconnect_voice(self, guild_id: int) -> None:
        self._runtime.disconnect_voice(guild_id)

    def send_text_message(self, channel_id: int, content: str) -> bool:
        return bool(self._runtime.send_text_message(channel_id, content))

    def send_voice_pcm(self, guild_id: int, pcm_s16le_stereo_48khz: bytes) -> bool:
        return bool(self._runtime.send_voice_pcm(guild_id, pcm_s16le_stereo_48khz))

    def attach_voice_input_ring(
        self,
        bus: SharedMemoryBus,
        capacity_bytes: int,
        *,
        initialize: bool = True,
    ) -> None:
        self._runtime.attach_voice_input_ring(
            bus.object_name(ChannelName.VOICE_PCM_IN),
            capacity_bytes,
            initialize,
        )

    def voice_input_ring_attached(self) -> bool:
        return bool(self._runtime.voice_input_ring_attached())

    def attach_voice_output_ring(
        self,
        bus: SharedMemoryBus,
        capacity_bytes: int,
        *,
        initialize: bool = True,
    ) -> None:
        self._runtime.attach_voice_output_ring(
            bus.object_name(ChannelName.TTS_PCM_OUT),
            capacity_bytes,
            initialize,
        )

    def voice_output_ring_attached(self) -> bool:
        return bool(self._runtime.voice_output_ring_attached())

    def pump_voice_output_once(self, guild_id: int, max_frame_bytes: int = 8192) -> bool:
        return bool(self._runtime.pump_voice_output_once(guild_id, max_frame_bytes))

    def poll_text_event(self) -> NativeDiscordTextEvent | None:
        event = self._runtime.pop_text_event()
        if event is None:
            return None
        return NativeDiscordTextEvent(
            guild_id=int(event.guild_id),
            channel_id=int(event.channel_id),
            message_id=int(event.message_id),
            author_id=int(event.author_id),
            content=str(event.content),
            author_is_bot=bool(event.author_is_bot),
        )

    def poll_voice_frame(self) -> NativeDiscordVoiceFrame | None:
        frame = self._runtime.pop_voice_frame()
        if frame is None:
            return None
        return NativeDiscordVoiceFrame(
            user_id=int(frame["user_id"]),
            pcm_s16le_stereo_48khz=bytes(frame["pcm_s16le_stereo_48khz"]),
        )
