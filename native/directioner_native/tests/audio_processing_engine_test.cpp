#include <cassert>
#include "directioner_native/audio/processing_engine.hpp"

using namespace directioner_native::audio;

void test_processing_engine_lifecycle() {
    ProcessingEngine engine;
    
    assert(!engine.running());
    
    engine.start();
    assert(engine.running());
    
    // Start again should be no-op
    engine.start();
    assert(engine.running());
    
    engine.stop();
    assert(!engine.running());
}

void test_processing_engine_stats() {
    ProcessingEngine engine;
    ProcessingStats stats = engine.stats();
    
    // Verify stats struct fields exist and are initialized to 0
    assert(stats.frames_in == 0);
    assert(stats.frames_out == 0);
    assert(stats.clipped_frames == 0);
    assert(stats.vad_speech_frames == 0);
    
    engine.start();
    assert(engine.running());
    
    // Stats should still be accessible
    stats = engine.stats();
    assert(stats.frames_in == 0);
    
    engine.stop();
}

int main() {
    test_processing_engine_lifecycle();
    test_processing_engine_stats();
    return 0;
}
