#include "directioner_native/shared_memory/spsc_ring_buffer.hpp"

#include <algorithm>
#include <cstring>
#include <limits>
#include <memory>
#include <stdexcept>

namespace directioner_native::shared_memory {
namespace {

void write_bytes(
    std::span<std::byte> ring,
    const std::uint64_t sequence,
    std::span<const std::byte> source) noexcept {
  const auto capacity = ring.size();
  const auto offset = static_cast<std::size_t>(sequence % capacity);
  const auto first = std::min(source.size(), capacity - offset);

  std::memcpy(ring.data() + offset, source.data(), first);
  if (first < source.size()) {
    std::memcpy(ring.data(), source.data() + first, source.size() - first);
  }
}

void read_bytes(
    std::span<const std::byte> ring,
    const std::uint64_t sequence,
    std::span<std::byte> target) noexcept {
  const auto capacity = ring.size();
  const auto offset = static_cast<std::size_t>(sequence % capacity);
  const auto first = std::min(target.size(), capacity - offset);

  std::memcpy(target.data(), ring.data() + offset, first);
  if (first < target.size()) {
    std::memcpy(target.data() + first, ring.data(), target.size() - first);
  }
}

}  // namespace

std::size_t SpscRingBufferView::required_bytes(const std::size_t capacity_bytes) noexcept {
  return sizeof(RingBufferHeader) + capacity_bytes;
}

void SpscRingBufferView::initialize(
    std::span<std::byte> memory,
    const std::size_t capacity_bytes) {
  if (memory.size() < required_bytes(capacity_bytes)) {
    throw std::invalid_argument("shared-memory region is too small for ring buffer");
  }

  auto* header = reinterpret_cast<RingBufferHeader*>(memory.data());
  std::construct_at(header);
  header->magic = ring_magic;
  header->abi_version = ring_abi_version;
  header->header_bytes = sizeof(RingBufferHeader);
  header->capacity_bytes = capacity_bytes;
  header->write_sequence.store(0, std::memory_order_relaxed);
  header->read_sequence.store(0, std::memory_order_relaxed);
  header->dropped_frames.store(0, std::memory_order_relaxed);

  auto payload = memory.subspan(sizeof(RingBufferHeader), capacity_bytes);
  std::fill(payload.begin(), payload.end(), std::byte{0});
}

SpscRingBufferView::SpscRingBufferView(std::span<std::byte> memory)
    : header_(nullptr),
      data_() {
  if (memory.size() < sizeof(RingBufferHeader)) {
    throw std::invalid_argument("shared-memory region is smaller than ring header");
  }

  header_ = reinterpret_cast<RingBufferHeader*>(memory.data());
  if (header_->magic != ring_magic || header_->abi_version != ring_abi_version) {
    throw std::invalid_argument("shared-memory ring header has incompatible ABI");
  }
  if (memory.size() < required_bytes(header_->capacity_bytes)) {
    throw std::invalid_argument("shared-memory region does not match ring capacity");
  }
  data_ = memory.subspan(sizeof(RingBufferHeader), header_->capacity_bytes);
}

bool SpscRingBufferView::try_write(std::span<const std::byte> frame) noexcept {
  if (frame.size() > std::numeric_limits<std::uint32_t>::max()) {
    header_->dropped_frames.fetch_add(1, std::memory_order_relaxed);
    return false;
  }

  const auto length = static_cast<std::uint32_t>(frame.size());
  const auto required = sizeof(length) + frame.size();
  if (required > capacity_bytes() || free_bytes() < required) {
    header_->dropped_frames.fetch_add(1, std::memory_order_relaxed);
    return false;
  }

  const auto write_sequence = header_->write_sequence.load(std::memory_order_relaxed);
  std::byte length_bytes[sizeof(length)]{};
  std::memcpy(length_bytes, &length, sizeof(length));

  write_bytes(data_, write_sequence, std::span<const std::byte>(length_bytes, sizeof(length_bytes)));
  write_bytes(data_, write_sequence + sizeof(length), frame);
  header_->write_sequence.store(write_sequence + required, std::memory_order_release);
  return true;
}

bool SpscRingBufferView::try_read(
    std::span<std::byte> out,
    std::size_t& bytes_read) noexcept {
  bytes_read = 0;
  const auto read_sequence = header_->read_sequence.load(std::memory_order_relaxed);
  const auto write_sequence = header_->write_sequence.load(std::memory_order_acquire);
  const auto available = write_sequence - read_sequence;
  if (available < sizeof(std::uint32_t)) {
    return false;
  }

  std::byte length_bytes[sizeof(std::uint32_t)]{};
  read_bytes(data_, read_sequence, std::span<std::byte>(length_bytes, sizeof(length_bytes)));

  std::uint32_t length = 0;
  std::memcpy(&length, length_bytes, sizeof(length));
  const auto required = sizeof(length) + static_cast<std::size_t>(length);
  if (available < required || out.size() < length) {
    return false;
  }

  read_bytes(data_, read_sequence + sizeof(length), out.subspan(0, length));
  bytes_read = length;
  header_->read_sequence.store(read_sequence + required, std::memory_order_release);
  return true;
}

std::size_t SpscRingBufferView::capacity_bytes() const noexcept {
  return static_cast<std::size_t>(header_->capacity_bytes);
}

std::size_t SpscRingBufferView::available_bytes() const noexcept {
  const auto write_sequence = header_->write_sequence.load(std::memory_order_acquire);
  const auto read_sequence = header_->read_sequence.load(std::memory_order_acquire);
  return static_cast<std::size_t>(write_sequence - read_sequence);
}

std::size_t SpscRingBufferView::free_bytes() const noexcept {
  return capacity_bytes() - available_bytes();
}

std::uint64_t SpscRingBufferView::dropped_frames() const noexcept {
  return header_->dropped_frames.load(std::memory_order_relaxed);
}

}  // namespace directioner_native::shared_memory
