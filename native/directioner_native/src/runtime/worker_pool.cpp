#include "directioner_native/runtime/worker_pool.hpp"

#include <chrono>

namespace directioner_native::runtime {

WorkerPool::~WorkerPool() {
  stop();
}

void WorkerPool::start(const std::size_t thread_count) {
  if (running_.exchange(true)) {
    return;
  }

  threads_.reserve(thread_count);
  for (std::size_t index = 0; index < thread_count; ++index) {
    threads_.emplace_back([this](std::stop_token token) {
      while (!token.stop_requested() && running_.load(std::memory_order_acquire)) {
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
      }
    });
  }
}

void WorkerPool::stop() noexcept {
  running_.store(false, std::memory_order_release);
  for (auto& thread : threads_) {
    thread.request_stop();
  }
  threads_.clear();
}

bool WorkerPool::running() const noexcept {
  return running_.load(std::memory_order_acquire);
}

std::size_t WorkerPool::thread_count() const noexcept {
  return threads_.size();
}

}  // namespace directioner_native::runtime

