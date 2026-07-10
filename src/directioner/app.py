"""Application entry point."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Sequence
from pathlib import Path

from directioner.config.settings import Settings
from directioner.monitoring import configure_logging, event_fields, get_logger

LOGGER = get_logger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="directioner")
    parser.add_argument(
        "--config",
        default=None,
        help="Path to the main YAML configuration file.",
    )
    subcommands = parser.add_subparsers(dest="command")
    subcommands.add_parser("check", help="Load configuration and report runtime readiness.")
    subcommands.add_parser(
        "validate-env",
        help="Validate required environment and configuration settings.",
    )
    subcommands.add_parser(
        "health-check",
        help="Run a lightweight runtime health report and emit JSON.",
    )
    subcommands.add_parser("native-smoke", help="Verify the native extension and shared memory.")
    subcommands.add_parser("dpp-smoke", help="Construct a DPP cluster without connecting.")
    run_discord = subcommands.add_parser("run-discord", help="Start the native DPP Discord runtime.")
    run_discord.add_argument(
        "--timeout-seconds",
        type=float,
        default=0.0,
        help="Stop automatically after this many seconds. 0 means run until interrupted.",
    )
    run_discord_bridge = subcommands.add_parser(
        "run-discord-bridge",
        help="Start the standalone DPP process and bridge events into Python.",
    )
    run_discord_bridge.add_argument(
        "--runtime",
        default=r".\build\release-dpp-vs\native\directioner_native\directioner_dpp_runtime.exe",
        help="Path to the standalone DPP runtime executable.",
    )
    run_discord_bridge.add_argument(
        "--timeout-seconds",
        type=float,
        default=0.0,
        help="Stop automatically after this many seconds. 0 means run until interrupted.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    configure_logging()
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = Settings.load(args.config)
    LOGGER.info(
        "app.command %s",
        event_fields(command=args.command or "check", env=settings.environment),
    )

    command = args.command or "check"
    if command == "check":
        issues = settings.validate_environment(require_discord_token=False)
        print(f"Directioner ready: {settings.app_name}")
        print(f"Environment: {settings.environment}")
        print(f"Discord token configured: {bool(settings.discord.bot_token)}")
        if issues:
            print(f"Validation issues: {len(issues)}")
            for issue in issues:
                print(f"- {issue}")
        return 0

    if command == "validate-env":
        return _validate_env(settings)

    if command == "health-check":
        return _health_check(settings)

    if command == "native-smoke":
        return _native_smoke()

    if command == "dpp-smoke":
        return _dpp_smoke(settings)

    if command == "run-discord":
        return asyncio.run(_run_discord(settings, timeout_seconds=args.timeout_seconds))

    if command == "run-discord-bridge":
        return asyncio.run(
            _run_discord_bridge(
                settings,
                runtime_path=Path(args.runtime),
                timeout_seconds=args.timeout_seconds,
            )
        )

    parser.error(f"Unknown command: {command}")
    return 0


async def _run_discord(settings: Settings, timeout_seconds: float = 0.0) -> int:
    from directioner.audio.shared_memory import ChannelName, SharedMemoryBus
    from directioner.audio.native_shared_memory import NativeSharedMemoryRing
    from directioner.audio.voice_input import VoiceInputReader
    from directioner.audio.voice_output import VoiceOutputWriter
    from directioner.audio.voice_output_pipeline import VoiceOutputPipeline
    from directioner.audio.voice_pipeline import VoiceInputPipeline
    from directioner.audio.vad import SileroVad
    from directioner.audio.wakeword import OpenWakeWordDetector
    from directioner.conversation.manager import build_conversation_router
    from directioner.diarization.service import DiarizationService
    from directioner.discord import DppDiscordRuntime, DppEventPump
    from directioner.discord.chat_output import DppChatSender
    from directioner.native import native_build_info
    from directioner.response.router import ResponseRouter
    from directioner.stt.parakeet_stream import ParakeetStreamingStt
    from directioner.text.cleanup import TextCleanup
    from directioner.tts.chatterbox_stream import ChatterboxStreamingTts

    print(f"Native extension: {native_build_info()}", flush=True)
    print("Preparing shared-memory voice rings...", flush=True)
    runtime = DppDiscordRuntime(settings.discord)
    shared_memory_bus = SharedMemoryBus(settings.runtime.shared_memory_namespace)
    voice_in_spec = shared_memory_bus.channels[ChannelName.VOICE_PCM_IN]
    voice_out_spec = shared_memory_bus.channels[ChannelName.TTS_PCM_OUT]
    runtime.attach_voice_input_ring(shared_memory_bus, voice_in_spec.ring_capacity_bytes)
    runtime.attach_voice_output_ring(shared_memory_bus, voice_out_spec.ring_capacity_bytes)

    voice_in_ring = NativeSharedMemoryRing.create_or_open(
        shared_memory_bus, ChannelName.VOICE_PCM_IN, voice_in_spec.ring_capacity_bytes
    )
    voice_out_ring = NativeSharedMemoryRing.create_or_open(
        shared_memory_bus, ChannelName.TTS_PCM_OUT, voice_out_spec.ring_capacity_bytes
    )

    vad = SileroVad(threshold=settings.vad.threshold) if settings.vad.enabled else None
    wakeword = (
        OpenWakeWordDetector(
            model_paths=list(settings.wakeword.model_paths),
            threshold=settings.wakeword.threshold,
            inference_framework=settings.wakeword.inference_framework,
        )
        if settings.wakeword.enabled
        else None
    )
    diarization = DiarizationService()
    stt = ParakeetStreamingStt(model_name=settings.stt.model)
    tts = ChatterboxStreamingTts(
        device=settings.tts.device,
        exaggeration=settings.tts.exaggeration,
        cfg_weight=settings.tts.cfg_weight,
    )
    writer = VoiceOutputWriter(voice_out_ring)
    voice_out_pipeline = VoiceOutputPipeline(writer=writer, tts=tts)

    chat_sender = DppChatSender(runtime)
    router = build_conversation_router(
        ResponseRouter(chat_sender=chat_sender, llm_settings=settings.llm),
        settings.conversation,
        settings.memory,
        voice_output_pipeline=voice_out_pipeline,
        tts=tts,
        voice_output=writer,
    )

    reader = VoiceInputReader(voice_in_ring)
    voice_in_pipeline = VoiceInputPipeline(
        reader=reader,
        diarization=diarization,
        stt=stt,
        cleanup=TextCleanup(),
        router=router,
        conversation_id=settings.runtime.shared_memory_namespace,
        vad=vad,
        wakeword=wakeword,
        require_wakeword=settings.wakeword.enabled,
    )

    event_pump = DppEventPump(runtime, router)

    print("Starting native DPP Discord runtime...", flush=True)
    runtime.start()
    print(f"Native DPP Discord runtime started: running={runtime.running()}", flush=True)
    print("Press Ctrl+C to stop.", flush=True)
    try:
        if timeout_seconds > 0:
            await asyncio.wait_for(
                _run_discord_loops(event_pump, voice_in_pipeline),
                timeout=timeout_seconds,
            )
        else:
            await _run_discord_loops(event_pump, voice_in_pipeline)
    except TimeoutError:
        print(f"Discord runtime timeout reached after {timeout_seconds:.1f}s.", flush=True)
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print(f"Discord runtime failed: {exc}", flush=True)
        raise
    finally:
        print("Stopping native DPP Discord runtime...", flush=True)
        runtime.stop()
        voice_in_ring.close()
        voice_out_ring.close()
    return 0


async def _run_discord_bridge(
    settings: Settings,
    runtime_path: Path,
    timeout_seconds: float = 0.0,
) -> int:
    from directioner.audio.shared_memory import ChannelName, SharedMemoryBus
    from directioner.audio.native_shared_memory import NativeSharedMemoryRing
    from directioner.audio.voice_input import VoiceInputReader
    from directioner.audio.voice_output import VoiceOutputWriter
    from directioner.audio.voice_output_pipeline import VoiceOutputPipeline
    from directioner.audio.voice_pipeline import VoiceInputPipeline
    from directioner.audio.vad import SileroVad
    from directioner.audio.wakeword import OpenWakeWordDetector
    from directioner.conversation.manager import build_conversation_router
    from directioner.diarization.service import DiarizationService
    from directioner.discord import DppEventPump
    from directioner.discord.standalone_process import (
        StandaloneDppChatSender,
        StandaloneDppOptions,
        StandaloneDppProcess,
    )
    from directioner.native import native_build_info
    from directioner.response.router import ResponseRouter
    from directioner.stt.parakeet_stream import ParakeetStreamingStt
    from directioner.text.cleanup import TextCleanup
    from directioner.tts.chatterbox_stream import ChatterboxStreamingTts

    print(f"Native extension: {native_build_info()}", flush=True)
    print(f"Starting standalone DPP Python bridge: {runtime_path}", flush=True)

    process = StandaloneDppProcess(
        settings.discord,
        StandaloneDppOptions(
            runtime_path=runtime_path,
            timeout_seconds=timeout_seconds,
        ),
    )

    # Voice pipeline components
    shared_memory_bus = SharedMemoryBus(settings.runtime.shared_memory_namespace)
    voice_in_spec = shared_memory_bus.channels[ChannelName.VOICE_PCM_IN]
    voice_out_spec = shared_memory_bus.channels[ChannelName.TTS_PCM_OUT]
    voice_in_ring = NativeSharedMemoryRing.create_or_open(
        shared_memory_bus, ChannelName.VOICE_PCM_IN, voice_in_spec.ring_capacity_bytes
    )
    voice_out_ring = NativeSharedMemoryRing.create_or_open(
        shared_memory_bus, ChannelName.TTS_PCM_OUT, voice_out_spec.ring_capacity_bytes
    )

    vad = SileroVad(threshold=settings.vad.threshold) if settings.vad.enabled else None
    wakeword = (
        OpenWakeWordDetector(
            model_paths=list(settings.wakeword.model_paths),
            threshold=settings.wakeword.threshold,
            inference_framework=settings.wakeword.inference_framework,
        )
        if settings.wakeword.enabled
        else None
    )
    diarization = DiarizationService()
    stt = ParakeetStreamingStt(model_name=settings.stt.model)
    tts = ChatterboxStreamingTts(
        device=settings.tts.device,
        exaggeration=settings.tts.exaggeration,
        cfg_weight=settings.tts.cfg_weight,
    )
    writer = VoiceOutputWriter(voice_out_ring)
    voice_out_pipeline = VoiceOutputPipeline(writer=writer, tts=tts)

    chat_sender = StandaloneDppChatSender(process)
    router = build_conversation_router(
        ResponseRouter(chat_sender=chat_sender, llm_settings=settings.llm),
        settings.conversation,
        settings.memory,
        voice_output_pipeline=voice_out_pipeline,
        tts=tts,
        voice_output=writer,
    )

    reader = VoiceInputReader(voice_in_ring)
    voice_in_pipeline = VoiceInputPipeline(
        reader=reader,
        diarization=diarization,
        stt=stt,
        cleanup=TextCleanup(),
        router=router,
        conversation_id=settings.runtime.shared_memory_namespace,
        vad=vad,
        wakeword=wakeword,
        require_wakeword=settings.wakeword.enabled,
    )

    event_pump = DppEventPump(process, router)  # type: ignore[arg-type]

    await process.start()
    print("Standalone DPP bridge started. Press Ctrl+C to stop.", flush=True)
    try:
        while process.running():
            chat_routed = await event_pump.drain_once()
            voice_routed = await voice_in_pipeline.drain_once()
            if chat_routed == 0 and voice_routed == 0:
                await asyncio.sleep(0.02)
    except KeyboardInterrupt:
        pass
    finally:
        print("Stopping standalone DPP bridge...", flush=True)
        await process.stop()
        voice_in_ring.close()
        voice_out_ring.close()
    return 0


async def _run_discord_loops(event_pump, voice_in_pipeline) -> None:
    """Run chat event pump and voice input pipeline concurrently."""
    while event_pump._runtime.running():
        chat_routed = await event_pump.drain_once()
        voice_routed = await voice_in_pipeline.drain_once()
        if chat_routed == 0 and voice_routed == 0:
            await asyncio.sleep(0.02)


def _native_smoke() -> int:
    from directioner.audio import (
        ChannelName,
        NativeSharedMemoryRing,
        PcmFormat,
        PcmFrameFlags,
        PcmFrameHeader,
        SharedMemoryBus,
        pack_pcm_frame_header,
        parse_pcm_frame,
    )
    from directioner.native import native_build_info

    print(f"Native extension: {native_build_info()}")
    bus = SharedMemoryBus("directioner-cli-smoke")
    ring = NativeSharedMemoryRing.create_or_open(bus, ChannelName.VOICE_PCM_IN, 4096)
    header = PcmFrameHeader(
        schema_version=1,
        header_bytes=48,
        stream_id=1,
        sequence=2,
        capture_time_ns=3,
        sample_rate_hz=48_000,
        channels=2,
        sample_format=PcmFormat.S16LE,
        frame_samples=1,
        speaker_hint=7,
        flags=PcmFrameFlags.SPEECH,
    )
    ok = ring.write_frame(pack_pcm_frame_header(header) + b"\x01\x00\x02\x00")
    raw = ring.read_frame(1024)
    ring.close()
    if raw is None:
        raise RuntimeError("Native shared-memory smoke test wrote no readable frame")
    frame = parse_pcm_frame(raw)
    print(
        "Shared-memory smoke: "
        f"write={ok} stream_id={frame.stream_id} sequence={frame.sequence} "
        f"payload_bytes={len(frame.payload)}"
    )
    return 0


def _dpp_smoke(settings: Settings) -> int:
    from directioner.discord import DppDiscordRuntime

    runtime = DppDiscordRuntime(settings.discord)
    print(runtime.construct_smoke(), flush=True)
    return 0


def _validate_env(settings: Settings) -> int:
    issues = settings.validate_environment(require_discord_token=True)
    if not issues:
        print("Environment validation passed.", flush=True)
        return 0

    print("Environment validation failed:", flush=True)
    for issue in issues:
        print(f"- {issue}", flush=True)
    return 1


def _health_check(settings: Settings) -> int:
    issues = list(settings.validate_environment(require_discord_token=False))
    native_ok = True
    native_error = ""

    try:
        from directioner.native import native_build_info

        native_info = native_build_info()
    except Exception as exc:
        native_ok = False
        native_info = ""
        native_error = str(exc)

    report = {
        "status": "ok" if native_ok and not issues else "degraded",
        "app_name": settings.app_name,
        "environment": settings.environment,
        "discord_token_configured": bool(settings.discord.bot_token),
        "llm_provider": settings.llm.provider,
        "native_extension": {
            "ok": native_ok,
            "info": native_info,
            "error": native_error,
        },
        "issues": issues,
    }
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
