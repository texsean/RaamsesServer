# Logging component CMakeLists.txt

add_library(rgs_logging STATIC
    Logger.cpp
)

target_include_directories(rgs_logging PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}
)
