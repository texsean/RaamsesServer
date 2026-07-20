#pragma once

#include <string>
#include <optional>

namespace rgs {

/**
 * Verification engine for agent task output.
 * Detects hallucinations, infinite loops, and policy violations.
 */
class Verifier {
public:
    Verifier() = default;

    // Verify agent output using specified methodology
    std::string verify(const std::string& agent_id,
                       const std::string& methodology = "auto") const;

private:
    // Methodology-specific checks
    bool check_local_llm(const std::string& agent_id) const;
    bool check_filebased(const std::string& agent_id) const;
};

} // namespace rgs
