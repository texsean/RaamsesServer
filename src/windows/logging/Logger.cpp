/**
 * RGS Windows Logging stub
 */

#include "Logger.h"
#include <iostream>
#include <fstream>
#include <chrono>
#include <iomanip>
#include <sstream>

namespace rgs {

static std::ofstream g_log_file;

void Logger::init(const std::string& log_file) {
    g_log_file.open(log_file, std::ios::app);
}

static std::string timestamp() {
    auto now = std::chrono::system_clock::now();
    auto time_t = std::chrono::system_clock::to_time_t(now);
    auto ms = std::chrono::duration_cast<std::chrono::milliseconds>(
        now.time_since_epoch()) % 1000;
    std::tm tm_buf;
#ifdef _WIN32
    localtime_s(&tm_buf, &time_t);
#else
    localtime_r(&time_t, &tm_buf);
#endif
    std::ostringstream oss;
    oss << std::put_time(&tm_buf, "%H:%M:%S")
        << "." << std::setfill('0') << std::setw(3) << ms.count();
    return oss.str();
}

void Logger::info(const std::string& msg) {
    std::cout << "[" << timestamp() << "] [INFO] " << msg << std::endl;
    if (g_log_file.is_open()) {
        g_log_file << "[" << timestamp() << "] [INFO] " << msg << "\n";
    }
}

void Logger::warn(const std::string& msg) {
    std::cerr << "[" << timestamp() << "] [WARN] " << msg << std::endl;
    if (g_log_file.is_open()) {
        g_log_file << "[" << timestamp() << "] [WARN] " << msg << "\n";
    }
}

void Logger::error(const std::string& msg) {
    std::cerr << "[" << timestamp() << "] [ERROR] " << msg << std::endl;
    if (g_log_file.is_open()) {
        g_log_file << "[" << timestamp() << "] [ERROR] " << msg << "\n";
    }
}

} // namespace rgs
