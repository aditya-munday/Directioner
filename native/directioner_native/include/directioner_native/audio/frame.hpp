#pragma once

#include <cstdint>

namespace directioner_native::audio {

enum class SampleFormat : std::uint16_t {
  S16Le = 1,
  F32Le = 2,
};

enum class PcmFrameFlag : std::uint32_t {
  None = 0,
  Speech = 1u << 0u,
  Silence = 1u << 1u,
  Clipped = 1u << 2u,
  PacketLossConcealment = 1u << 3u,
  Final = 1u << 4u,
};

#pragma pack(push, 1)
struct PcmFrameHeader {
  std::uint16_t schema_version = 1;
  std::uint16_t header_bytes = sizeof(PcmFrameHeader);
  std::uint64_t stream_id = 0;
  std::uint64_t sequence = 0;
  std::uint64_t capture_time_ns = 0;
  std::uint32_t sample_rate_hz = 48000;
  std::uint16_t channels = 1;
  SampleFormat sample_format = SampleFormat::S16Le;
  std::uint32_t frame_samples = 0;
  std::uint32_t speaker_hint = 0;
  std::uint32_t flags = 0;
};
#pragma pack(pop)

static_assert(sizeof(PcmFrameHeader) == 48);

}  // namespace directioner_native::audio
