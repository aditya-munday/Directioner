#include <thread>
#include <chrono>
#include <cassert>
#include "directioner_native/runtime/worker_pool.hpp"

using namespace directioner_native::runtime;

void test_worker_pool_lifecycle() {
    WorkerPool pool;
    assert(!pool.running());
    assert(pool.thread_count() == 0);
    
    pool.start(4);
    assert(pool.running());
    assert(pool.thread_count() == 4);
    
    // Starting again should be no-op
    pool.start(2);
    assert(pool.running());
    assert(pool.thread_count() == 4);
    
    pool.stop();
    assert(!pool.running());
    assert(pool.thread_count() == 0);
}

void test_worker_pool_zero_threads() {
    WorkerPool pool;
    pool.start(0);  // Should use minimum of 1
    assert(pool.running());
    assert(pool.thread_count() == 1);
    pool.stop();
}

void test_worker_pool_destructor_stops() {
    // Verify destructor doesn't crash when pool is running
    {
        WorkerPool pool;
        pool.start(2);
        assert(pool.running());
        // pool goes out of scope - destructor should call stop()
    }
    // If we get here without crashing, the test passed
}

int main() {
    test_worker_pool_lifecycle();
    test_worker_pool_zero_threads();
    test_worker_pool_destructor_stops();
    return 0;
}
