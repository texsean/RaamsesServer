# Verifier component CMakeLists.txt

add_library(rgs_verifier STATIC
    Verifier.cpp
)

target_include_directories(rgs_verifier PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${CMAKE_CURRENT_SOURCE_DIR}/..
)

target_link_libraries(rgs_verifier PUBLIC
    rgs_logging
)
