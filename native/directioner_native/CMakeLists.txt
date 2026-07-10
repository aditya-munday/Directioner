option(DIRECTIONER_WITH_DPP "Build the native Discord runtime with DPP" ON)

if(DIRECTIONER_WITH_DPP)
  find_package(dpp CONFIG REQUIRED)
endif()

set(DIRECTIONER_NATIVE_SOURCES
  bindings/module.cpp
  src/audio/processing_engine.cpp
  src/discord/voice_gateway.cpp
  src/runtime/worker_pool.cpp
  src/shared_memory/mapped_region.cpp
  src/shared_memory/spsc_ring_buffer.cpp
)

nanobind_add_module(_native NB_STATIC ${DIRECTIONER_NATIVE_SOURCES})

# C++ Unit Tests
enable_testing()

add_executable(worker_pool_test tests/worker_pool_test.cpp src/runtime/worker_pool.cpp)
target_compile_features(worker_pool_test PRIVATE cxx_std_20)
target_include_directories(worker_pool_test PRIVATE include)
if(MSVC)
  target_compile_options(worker_pool_test PRIVATE /W4 /permissive-)
else()
  target_compile_options(worker_pool_test PRIVATE -Wall -Wextra -Wpedantic)
endif()
add_test(NAME native.worker_pool_test COMMAND worker_pool_test)

add_executable(spsc_ring_buffer_test tests/spsc_ring_buffer_test.cpp src/shared_memory/spsc_ring_buffer.cpp)
target_compile_features(spsc_ring_buffer_test PRIVATE cxx_std_20)
target_include_directories(spsc_ring_buffer_test PRIVATE include)
if(MSVC)
  target_compile_options(spsc_ring_buffer_test PRIVATE /W4 /permissive-)
else()
  target_compile_options(spsc_ring_buffer_test PRIVATE -Wall -Wextra -Wpedantic)
endif()
add_test(NAME native.spsc_ring_buffer_test COMMAND spsc_ring_buffer_test)

add_executable(audio_processing_engine_test tests/audio_processing_engine_test.cpp src/audio/processing_engine.cpp)
target_compile_features(audio_processing_engine_test PRIVATE cxx_std_20)
target_include_directories(audio_processing_engine_test PRIVATE include)
if(MSVC)
  target_compile_options(audio_processing_engine_test PRIVATE /W4 /permissive-)
else()
  target_compile_options(audio_processing_engine_test PRIVATE -Wall -Wextra -Wpedantic)
endif()
add_test(NAME native.audio_processing_engine_test COMMAND audio_processing_engine_test)

set_target_properties(_native
  PROPERTIES
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_SOURCE_DIR}/src/directioner"
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_SOURCE_DIR}/src/directioner"
)

target_include_directories(_native
  PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_compile_features(_native PRIVATE cxx_std_20)

target_compile_definitions(_native
  PRIVATE
    DIRECTIONER_WITH_DPP=$<BOOL:${DIRECTIONER_WITH_DPP}>
)

if(DIRECTIONER_WITH_DPP)
  target_link_libraries(_native PRIVATE dpp::dpp)
endif()

if(MSVC)
  target_compile_options(_native PRIVATE /W4 /permissive-)
else()
  target_compile_options(_native PRIVATE -Wall -Wextra -Wpedantic)
endif()

install(TARGETS _native
  LIBRARY DESTINATION directioner
  RUNTIME DESTINATION directioner
)

if(DIRECTIONER_WITH_DPP)
  add_executable(directioner_dpp_probe tools/dpp_probe.cpp)
  target_compile_features(directioner_dpp_probe PRIVATE cxx_std_20)
  target_link_libraries(directioner_dpp_probe PRIVATE dpp::dpp)
  add_executable(directioner_dpp_runtime tools/dpp_runtime_main.cpp)
  target_compile_features(directioner_dpp_runtime PRIVATE cxx_std_20)
  target_link_libraries(directioner_dpp_runtime PRIVATE dpp::dpp)
  if(MSVC)
    target_compile_options(directioner_dpp_probe PRIVATE /W4 /permissive-)
    target_compile_options(directioner_dpp_runtime PRIVATE /W4 /permissive-)
  else()
    target_compile_options(directioner_dpp_probe PRIVATE -Wall -Wextra -Wpedantic)
    target_compile_options(directioner_dpp_runtime PRIVATE -Wall -Wextra -Wpedantic)
  endif()
endif()
