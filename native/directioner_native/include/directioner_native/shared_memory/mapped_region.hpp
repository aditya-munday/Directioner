#pragma once

#include <cstddef>
#include <span>
#include <string>

namespace directioner_native::shared_memory {

enum class SharedMemoryOpenMode {
  CreateOrOpen,
  OpenExisting,
};

class SharedMemoryRegion {
 public:
  SharedMemoryRegion() = default;
  SharedMemoryRegion(const SharedMemoryRegion&) = delete;
  SharedMemoryRegion& operator=(const SharedMemoryRegion&) = delete;
  SharedMemoryRegion(SharedMemoryRegion&& other) noexcept;
  SharedMemoryRegion& operator=(SharedMemoryRegion&& other) noexcept;
  ~SharedMemoryRegion();

  static SharedMemoryRegion create_or_open(std::string name, std::size_t bytes);
  static SharedMemoryRegion open_existing(std::string name, std::size_t bytes);

  [[nodiscard]] std::span<std::byte> bytes() noexcept;
  [[nodiscard]] std::span<const std::byte> bytes() const noexcept;
  [[nodiscard]] const std::string& name() const noexcept;
  [[nodiscard]] std::size_t size() const noexcept;
  [[nodiscard]] bool mapped() const noexcept;

  void close() noexcept;

 private:
  SharedMemoryRegion(std::string name, std::size_t bytes, SharedMemoryOpenMode mode);

  std::string name_;
  std::size_t size_ = 0;
  void* view_ = nullptr;

#if defined(_WIN32)
  void* mapping_handle_ = nullptr;
#else
  int fd_ = -1;
#endif
};

}  // namespace directioner_native::shared_memory

