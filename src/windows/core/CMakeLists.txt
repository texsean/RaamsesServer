# Core component CMakeLists.txt
# Platform-agnostic core: config loading, protocol parsing

add_library(rgs_core STATIC
    ConfigLoader.cpp
)

target_include_directories(rgs_core PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}
)
