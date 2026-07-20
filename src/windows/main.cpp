/**
 * RGS Windows Server — Main entry point
 *
 * Cross-platform gateway server stub.
 * Windows build targets MSVC 2022+ with C++23.
 *
 * The core protocol logic is shared; platform-specific code
 * (networking, filesystem) is conditionally compiled.
 */

#include <iostream>
#include <string>
#include <csignal>
#include <atomic>

// Platform-specific includes
#ifdef _WIN32
    #include <windows.h>
    #define RGS_PLATFORM "Windows"
#else
    #include <unistd.h>
    #define RGS_PLATFORM "Unix"
#endif

#include "verifier/Verifier.h"
#include "logging/Logger.h"
#include "core/ConfigLoader.h"

using namespace rgs;

// Global shutdown flag
static std::atomic<bool> g_running{true};

#ifdef _WIN32
BOOL WINAPI CtrlHandler(DWORD fdwCtrlType) {
    if (fdwCtrlType == CTRL_C_EVENT) {
        g_running = false;
        return TRUE;
    }
    return FALSE;
}
#else
void signalHandler(int) {
    g_running = false;
}
#endif

int main(int argc, char* argv[]) {
    // Signal handler
#ifdef _WIN32
    SetConsoleCtrlHandler(CtrlHandler, TRUE);
#else
    signal(SIGTERM, signalHandler);
    signal(SIGINT, signalHandler);
#endif

    Logger::init("rgs_server.log");

    // Try to load config
    ConfigLoader config;
    std::string config_file = "rgs.config";
    if (argc > 1) {
        config_file = argv[1];
    }

    if (!config.load(config_file)) {
        Logger::warn("No config file found, using defaults");
    }

    // Platform banner
    std::cout << "RGS Windows Server v1.0.0 (" << RGS_PLATFORM << ")" << std::endl;
    std::cout << "Configuration: " << config_file << std::endl;
    std::cout << "Press Ctrl+C to stop" << std::endl;

    // Initialize verifier
    Verifier verifier;
    Logger::info("Verifier initialized");

    // TODO: Initialize gateway server (TCP listener)
    // TODO: Initialize device client pool
    // TODO: Start event loop

    Logger::info("Starting event loop...");

    // Simple event loop (replace with actual async I/O)
    while (g_running) {
        // Platform-specific event processing
#ifdef _WIN32
        Sleep(1000);  // 1-second tick
#else
        sleep(1);
#endif
    }

    Logger::info("Shutting down...");
    return 0;
}
