#include "directioner_native/shared_memory/mapped_region.hpp"

#include <cstdint>
#include <stdexcept>
#include <utility>

#if defined(_WIN32)
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <Windows.h>
#else
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#endif

namespace directioner_native::shared_memory {
namespace {

#if defined(_WIN32)
std::runtime_error last_platform_error(const char* prefix) {
  return std::runtime_error(std::string(prefix) + " failed with error " + std::to_string(GetLastError()));
}
#else
std::runtime_error last_platform_error(const char* prefix) {
  return std::runtime_error(std::string(prefix) + " failed");
}

std::string normalize_posix_name(const std::string& name) {
  if (!name.empty() && name.front() == '/') {
    return name;
  }
  return "/" + name;
}
#endif

}  // namespace

SharedMemoryRegion::SharedMemoryRegion(
    std::string name,
    const std::size_t bytes,
    const SharedMemoryOpenMode mode)
    : name_(std::move(name)), size_(bytes) {
  if (name_.empty()) {
    throw std::invalid_argument("shared-memory name cannot be empty");
  }
  if (size_ == 0) {
    throw std::invalid_argument("shared-memory size cannot be zero");
  }

#if defined(_WIN32)
  const auto access = PAGE_READWRITE;
  const auto size64 = static_cast<std::uint64_t>(size_);
  const auto size_high = static_cast<DWORD>((size64 >> 32U) & 0xffffffffU);
  const auto size_low = static_cast<DWORD>(size64 & 0xffffffffU);

  if (mode == SharedMemoryOpenMode::CreateOrOpen) {
    mapping_handle_ = CreateFileMappingA(
        INVALID_HANDLE_VALUE,
        nullptr,
        access,
        size_high,
        size_low,
        name_.c_str());
  } else {
    mapping_handle_ = OpenFileMappingA(FILE_MAP_ALL_ACCESS, FALSE, name_.c_str());
  }

  if (mapping_handle_ == nullptr) {
    throw last_platform_error("Create/OpenFileMappingA");
  }

  view_ = MapViewOfFile(mapping_handle_, FILE_MAP_ALL_ACCESS, 0, 0, size_);
  if (view_ == nullptr) {
    close();
    throw last_platform_error("MapViewOfFile");
  }
#else
  const auto normalized = normalize_posix_name(name_);
  const auto flags = mode == SharedMemoryOpenMode::CreateOrOpen ? (O_CREAT | O_RDWR) : O_RDWR;
  fd_ = shm_open(normalized.c_str(), flags, 0600);
  if (fd_ == -1) {
    throw last_platform_error("shm_open");
  }

  if (mode == SharedMemoryOpenMode::CreateOrOpen && ftruncate(fd_, static_cast<off_t>(size_)) == -1) {
    close();
    throw last_platform_error("ftruncate");
  }

  view_ = mmap(nullptr, size_, PROT_READ | PROT_WRITE, MAP_SHARED, fd_, 0);
  if (view_ == MAP_FAILED) {
    view_ = nullptr;
    close();
    throw last_platform_error("mmap");
  }
#endif
}

SharedMemoryRegion::SharedMemoryRegion(SharedMemoryRegion&& other) noexcept {
  *this = std::move(other);
}

SharedMemoryRegion& SharedMemoryRegion::operator=(SharedMemoryRegion&& other) noexcept {
  if (this == &other) {
    return *this;
  }

  close();
  name_ = std::move(other.name_);
  size_ = other.size_;
  view_ = other.view_;
  other.size_ = 0;
  other.view_ = nullptr;

#if defined(_WIN32)
  mapping_handle_ = other.mapping_handle_;
  other.mapping_handle_ = nullptr;
#else
  fd_ = other.fd_;
  other.fd_ = -1;
#endif

  return *this;
}

SharedMemoryRegion::~SharedMemoryRegion() {
  close();
}

SharedMemoryRegion SharedMemoryRegion::create_or_open(std::string name, const std::size_t bytes) {
  return SharedMemoryRegion(std::move(name), bytes, SharedMemoryOpenMode::CreateOrOpen);
}

SharedMemoryRegion SharedMemoryRegion::open_existing(std::string name, const std::size_t bytes) {
  return SharedMemoryRegion(std::move(name), bytes, SharedMemoryOpenMode::OpenExisting);
}

std::span<std::byte> SharedMemoryRegion::bytes() noexcept {
  return {static_cast<std::byte*>(view_), size_};
}

std::span<const std::byte> SharedMemoryRegion::bytes() const noexcept {
  return {static_cast<const std::byte*>(view_), size_};
}

const std::string& SharedMemoryRegion::name() const noexcept {
  return name_;
}

std::size_t SharedMemoryRegion::size() const noexcept {
  return size_;
}

bool SharedMemoryRegion::mapped() const noexcept {
  return view_ != nullptr && size_ > 0;
}

void SharedMemoryRegion::close() noexcept {
#if defined(_WIN32)
  if (view_ != nullptr) {
    UnmapViewOfFile(view_);
    view_ = nullptr;
  }
  if (mapping_handle_ != nullptr) {
    CloseHandle(mapping_handle_);
    mapping_handle_ = nullptr;
  }
#else
  if (view_ != nullptr) {
    munmap(view_, size_);
    view_ = nullptr;
  }
  if (fd_ != -1) {
    ::close(fd_);
    fd_ = -1;
  }
#endif
  size_ = 0;
}

}  // namespace directioner_native::shared_memory
