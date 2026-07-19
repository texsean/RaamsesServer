cmake_minimum_required(VERSION 3.20)
project(RGS LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# Find required packages
find_package(Threads REQUIRED)

# Main executable
add_executable(rgs_server
    main.cpp
    core/ConfigLoader.cpp
    logging/Logger.cpp
)

target_include_directories(rgs_server PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_link_libraries(rgs_server PRIVATE
    Threads::Threads
)

# Enable warnings
if(MSVC)
    target_compile_options(rgs_server PRIVATE /W4)
else()
    target_compile_options(rgs_server PRIVATE -Wall -Wextra -Wpedantic)
endif()
