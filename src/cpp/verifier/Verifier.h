#pragma once
#include <string>
#include <vector>

/**
 * Raamses Verifier
 * Supports: LocalLLM, FILEbased, auto, blink
 */
class Verifier {
public:
    struct Verdict {
        bool verified;
        double confidence;
        std::string status;
        std::string summary;
        std::vector<std::string> issues;
        std::string recommendation;
        std::string methodology_used;
    };

    Verifier(const std::string& configPath);
    Verdict verifyAgent(const std::string& agentId);

private:
    std::string methodology;
    std::string localModel = "llama3.2:3b";
    int maxLlmSeconds = 8;
};