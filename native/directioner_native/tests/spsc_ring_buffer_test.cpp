#include <cstring>
#include <cassert>
#include <vector>
#include <byte>
#include "directioner_native/shared_memory/spsc_ring_buffer.hpp"

using namespace directioner_native::shared_memory;

void test_required_bytes() {
    // Verify required_bytes calculation
    auto required = SpscRingBufferView::required_bytes(1024);
    assert(required > 1024);  // Must include header
    assert(required >= sizeof(RingBufferHeader) + 1024);
}

void test_initialize_and_view() {
    std::size_t capacity = 4096;
    std::size_t required = SpscRingBufferView::required_bytes(capacity);
    std::vector<std::byte> memory(required);
    
    SpscRingBufferView::initialize(memory, capacity);
    SpscRingBufferView view(memory);
    
    assert(view.capacity_bytes() == capacity);
    assert(view.available_bytes() == 0);
    assert(view.free_bytes() == capacity);
    assert(view.dropped_frames() == 0);
}

void test_write_read_single_frame() {
    std::size_t capacity = 4096;
    std::size_t required = SpscRingBufferView::required_bytes(capacity);
    std::vector<std::byte> memory(required);
    
    SpscRingBufferView::initialize(memory, capacity);
    SpscRingBufferView view(memory);
    
    // Write a frame
    const char* test_data = "Hello, Ring Buffer!";
    std::size_t data_len = std::strlen(test_data);
    std::span<const std::byte> frame(
        reinterpret_cast<const std::byte*>(test_data),
        data_len
    );
    
    assert(view.try_write(frame));
    assert(view.available_bytes() >= data_len);
    assert(view.free_bytes() <= capacity - data_len);
    
    // Read the frame
    std::vector<std::byte> read_buffer(data_len + 1);
    std::size_t bytes_read = 0;
    assert(view.try_read(read_buffer, bytes_read));
    assert(bytes_read == data_len);
    assert(std::strcmp(reinterpret_cast<const char*>(read_buffer.data()), test_data) == 0);
}

void test_dropped_frames() {
    std::size_t capacity = 64;  // Small capacity for testing
    std::size_t required = SpscRingBufferView::required_bytes(capacity);
    std::vector<std::byte> memory(required);
    
    SpscRingBufferView::initialize(memory, capacity);
    SpscRingBufferView view(memory);
    
    // Fill the buffer with frames larger than capacity
    const char large_data[] = "This is a very long message that exceeds buffer capacity";
    std::span<const std::byte> frame(
        reinterpret_cast<const std::byte*>(large_data),
        sizeof(large_data)
    );
    
    // Write multiple frames - some should be dropped
    int dropped_count = 0;
    for (int i = 0; i < 10; i++) {
        if (!view.try_write(frame)) {
            dropped_count++;
        }
    }
    
    assert(view.dropped_frames() == dropped_count || view.dropped_frames() > 0);
}

void test_empty_buffer_read() {
    std::size_t capacity = 1024;
    std::size_t required = SpscRingBufferView::required_bytes(capacity);
    std::vector<std::byte> memory(required);
    
    SpscRingBufferView::initialize(memory, capacity);
    SpscRingBufferView view(memory);
    
    // Try to read from empty buffer
    std::vector<std::byte> read_buffer(100);
    std::size_t bytes_read = 999;  // Set to non-zero to verify it doesn't change
    assert(!view.try_read(read_buffer, bytes_read));
    assert(bytes_read == 0);  // Should be set to 0 on failure
}

int main() {
    test_required_bytes();
    test_initialize_and_view();
    test_write_read_single_frame();
    test_dropped_frames();
    test_empty_buffer_read();
    return 0;
}
