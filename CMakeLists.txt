cmake_minimum_required(VERSION 3.25)

project(
  avsys
  VERSION 0.1.0
  DESCRIPTION "Audio Validation Systems Lab foundation"
  LANGUAGES CXX
)

option(AVSYS_BUILD_TESTS "Build native unit tests" ON)
option(AVSYS_BUILD_PYTHON "Build the minimal Python extension" OFF)
option(AVSYS_ENABLE_SANITIZERS "Enable AddressSanitizer and UndefinedBehaviorSanitizer" OFF)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_library(avsys_core STATIC cpp/src/native_runtime.cpp cpp/src/version.cpp)
add_library(avsys::core ALIAS avsys_core)
target_include_directories(
  avsys_core
  PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/cpp/include>
    $<INSTALL_INTERFACE:include>
)
target_compile_features(avsys_core PUBLIC cxx_std_20)
set_target_properties(avsys_core PROPERTIES POSITION_INDEPENDENT_CODE ON)

if(MSVC)
  target_compile_options(avsys_core PRIVATE /W4 /permissive-)
else()
  target_compile_options(avsys_core PRIVATE -Wall -Wextra -Wpedantic)
endif()

if(AVSYS_ENABLE_SANITIZERS)
  if(MSVC)
    message(FATAL_ERROR "AVSYS_ENABLE_SANITIZERS is supported only with Clang or GCC")
  endif()
  target_compile_options(avsys_core PUBLIC -fsanitize=address,undefined -fno-omit-frame-pointer)
  target_link_options(avsys_core PUBLIC -fsanitize=address,undefined)
endif()

if(AVSYS_BUILD_PYTHON)
  set(PYBIND11_FINDPYTHON ON)
  add_subdirectory(third_party/pybind11)
  pybind11_add_module(_native MODULE cpp/bindings/module.cpp)
  target_link_libraries(_native PRIVATE avsys::core)
  target_compile_features(_native PRIVATE cxx_std_20)
  install(TARGETS _native LIBRARY DESTINATION avsys RUNTIME DESTINATION avsys)
  install(FILES schemas/v1/baseline.schema.json
                schemas/v1/manifest.schema.json
                schemas/v1/result.schema.json
                schemas/v1/stimulus-metadata.schema.json
          DESTINATION avsys/schemas/v1)
endif()

include(CTest)
if(BUILD_TESTING AND AVSYS_BUILD_TESTS)
  set(BUILD_GMOCK OFF CACHE BOOL "" FORCE)
  set(INSTALL_GTEST OFF CACHE BOOL "" FORCE)
  add_subdirectory(third_party/googletest EXCLUDE_FROM_ALL)

  add_executable(
    avsys_native_tests
    cpp/tests/native_runtime_test.cpp
    cpp/tests/spsc_ring_buffer_test.cpp
    cpp/tests/version_test.cpp
  )
  target_link_libraries(avsys_native_tests PRIVATE avsys::core GTest::gtest_main)
  target_compile_features(avsys_native_tests PRIVATE cxx_std_20)

  include(GoogleTest)
  gtest_discover_tests(avsys_native_tests DISCOVERY_TIMEOUT 30)
endif()
