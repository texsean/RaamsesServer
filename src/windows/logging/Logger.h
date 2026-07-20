#pragma once

#include <string>

namespace rgs {

/**
 * Cross-platform logging interface.
 * Outputs to console + log file.
 */
class Logger {
public:
    static void init(const std::string& log_file);
    static void info(const std::string& msg);
    static void warn(const std::string& msg);
    static void error(const std::string& msg);

private:
    Logger() = delete;
};

} // namespace rgs
