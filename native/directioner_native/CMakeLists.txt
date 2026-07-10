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
