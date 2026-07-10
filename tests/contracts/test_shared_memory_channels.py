from directioner.audio.shared_memory import ChannelName, SharedMemoryBus


def test_shared_memory_channel_names_are_namespaced() -> None:
    bus = SharedMemoryBus("directioner-test")

    assert bus.object_name(ChannelName.VOICE_PCM_IN) == "directioner-test.voice_pcm_in"

