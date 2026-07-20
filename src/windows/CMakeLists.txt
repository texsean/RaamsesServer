# CMake configuration for RGS Windows build
# Compatible with MSVC 2022+ and C++23

cmake_minimum_required(VERSION 3.26)
project(RGS_Windows LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# Find required packages
find_package(Threads REQUIRED)

# ── Platform detection ────────────────────────────────────────────────────

if(WIN32)
    # Windows-specific settings
    set(CMAKE_WINDOWS_EXPORT_ALL_SYMBOLS ON)
    add_compile_options(/W4 /permissive-)
    add_definitions(-DUNICODE -D_UNICODE)
    message(STATUS "Building for Windows")
else()
    # Linux/macOS settings (for cross-compilation testing)
    add_compile_options(-Wall -Wextra -Wpedantic)
    message(STATUS "Building for Unix (cross-compile or native)")
endif()

# ── Subdirectories ────────────────────────────────────────────────────────

# Core components (portable C++)
add_subdirectory(core)
add_subdirectory(logging)
add_subdirectory(verifier)

# ── Main executable ───────────────────────────────────────────────────────

add_executable(rgs_server_windows
    main.cpp
)

target_include_directories(rgs_server_windows PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/core
    ${CMAKE_CURRENT_SOURCE_DIR}/logging
    ${CMAKE_CURRENT_SOURCE_DIR}/verifier
)

# ── Link dependencies ─────────────────────────────────────────────────────

target_link_libraries(rgs_server_windows PRIVATE
    rgs_core
    rgs_logging
    rgs_verifier
)

if(WIN32)
    # Windows networking: WS2_32 for Winsock
    target_link_libraries(rgs_server_windows PRIVATE ws2_32)
    # Threading (Windows API is built-in, but we use std::thread)
else()
    target_link_libraries(rgs_server_windows PRIVATE Threads::Threads)
endif()
