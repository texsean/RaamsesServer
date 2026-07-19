#include <iostream>
#include "core/ConfigLoader.h"
#include "logging/Logger.h"

int main(int argc, char* argv[]) {
    Logger::init("rgs_server.log");
    Logger::info("RAAMSES Server starting...");

    ConfigLoader config;
    if (!config.load("rgs.config")) {
        Logger::error("Failed to load configuration");
        return 1;
    }

    Logger::info("Configuration loaded successfully");
    Logger::info("Verifier methodology: " + config.getVerifierMethodology());

    // TODO: Initialize network, protocol, verifier, etc.

    Logger::info("RAAMSES Server shutdown complete");
    return 0;
}
