#include "directioner_native/audio/processing_engine.hpp"

namespace directioner_native::audio {

void ProcessingEngine::start() {
  running_.store(true, std::memory_order_release);
}

void ProcessingEngine::stop() noexcept {
  running_.store(false, std::memory_order_release);
}

bool ProcessingEngine::running() const noexcept {
  return running_.load(std::memory_order_acquire);
}

ProcessingStats ProcessingEngine::stats() const noexcept {
  return stats_;
}

}  // namespace directioner_native::audio

