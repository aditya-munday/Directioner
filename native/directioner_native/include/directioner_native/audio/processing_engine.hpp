#pragma once

#include <atomic>
#include <cstdint>

namespace directioner_native::audio {

struct ProcessingStats {
  std::uint64_t frames_in = 0;
  std::uint64_t frames_out = 0;
  std::uint64_t clipped_frames = 0;
  std::uint64_t vad_speech_frames = 0;
};

class ProcessingEngine {
 public:
  void start();
  void stop() noexcept;

  [[nodiscard]] bool running() const noexcept;
  [[nodiscard]] ProcessingStats stats() const noexcept;

 private:
  std::atomic_bool running_{false};
  ProcessingStats stats_{};
};

}  // namespace directioner_native::audio

