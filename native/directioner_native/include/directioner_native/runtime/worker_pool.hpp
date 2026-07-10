#pragma once

#include <atomic>
#include <cstddef>
#include <thread>
#include <vector>

namespace directioner_native::runtime {

class WorkerPool {
 public:
  WorkerPool() = default;
  WorkerPool(const WorkerPool&) = delete;
  WorkerPool& operator=(const WorkerPool&) = delete;
  ~WorkerPool();

  void start(std::size_t thread_count);
  void stop() noexcept;

  [[nodiscard]] bool running() const noexcept;
  [[nodiscard]] std::size_t thread_count() const noexcept;

 private:
  std::atomic_bool running_{false};
  std::vector<std::jthread> threads_;
};

}  // namespace directioner_native::runtime

