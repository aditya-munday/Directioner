#pragma once

#include <atomic>
#include <cstddef>
#include <cstdint>
#include <span>

namespace directioner_native::shared_memory {

inline constexpr std::uint32_t ring_magic = 0x4449524E;
inline constexpr std::uint16_t ring_abi_version = 1;

struct alignas(64) RingBufferHeader {
  std::uint32_t magic = ring_magic;
  std::uint16_t abi_version = ring_abi_version;
  std::uint16_t header_bytes = sizeof(RingBufferHeader);
  std::uint64_t capacity_bytes = 0;
  std::atomic<std::uint64_t> write_sequence = 0;
  std::atomic<std::uint64_t> read_sequence = 0;
  std::atomic<std::uint64_t> dropped_frames = 0;
};

class SpscRingBufferView {
 public:
  static std::size_t required_bytes(std::size_t capacity_bytes) noexcept;
  static void initialize(std::span<std::byte> memory, std::size_t capacity_bytes);

  explicit SpscRingBufferView(std::span<std::byte> memory);

  [[nodiscard]] bool try_write(std::span<const std::byte> frame) noexcept;
  [[nodiscard]] bool try_read(std::span<std::byte> out, std::size_t& bytes_read) noexcept;

  [[nodiscard]] std::size_t capacity_bytes() const noexcept;
  [[nodiscard]] std::size_t available_bytes() const noexcept;
  [[nodiscard]] std::size_t free_bytes() const noexcept;
  [[nodiscard]] std::uint64_t dropped_frames() const noexcept;

 private:
  RingBufferHeader* header_;
  std::span<std::byte> data_;
};

}  // namespace directioner_native::shared_memory

