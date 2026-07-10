#pragma once

#include <cstddef>
#include <cstdint>
#include <string_view>

namespace directioner_native::shared_memory {

enum class ChannelName : std::uint8_t {
  VoicePcmIn = 1,
  VoiceEventsIn = 2,
  TtsPcmOut = 3,
  VoiceControlOut = 4,
  MetricsNative = 5,
};

struct ChannelSpec {
  ChannelName name;
  std::string_view object_suffix;
  std::size_t frame_capacity;
  std::size_t max_frame_bytes;
  bool lossy;
};

inline constexpr ChannelSpec default_channels[] = {
    {ChannelName::VoicePcmIn, "voice_pcm_in", 512, 4096, true},
    {ChannelName::VoiceEventsIn, "voice_events_in", 256, 1024, true},
    {ChannelName::TtsPcmOut, "tts_pcm_out", 512, 4096, false},
    {ChannelName::VoiceControlOut, "voice_control_out", 64, 512, false},
    {ChannelName::MetricsNative, "metrics_native", 128, 1024, true},
};

}  // namespace directioner_native::shared_memory

