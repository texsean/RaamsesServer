#include "Logger.h"
#include <fstream>
#include <mutex>
#include <chrono>
#include <iomanip>

static std::ofstream logFile;
static std::mutex logMutex;

void Logger::init(const std::string& filename) {
    std::lock_guard<std::mutex> lock(logMutex);
    logFile.open(filename, std::ios::app);
}

void Logger::log(const std::string& level, const std::string& message) {
    std::lock_guard<std::mutex> lock(logMutex);
    auto now = std::chrono::system_clock::now();
    auto time = std::chrono::system_clock::to_time_t(now);

    if (logFile.is_open()) {
        logFile << std::put_time(std::localtime(&time), "%Y-%m-%d %H:%M:%S")
                << " [" << level << "] " << message << std::endl;
    }
}

void Logger::info(const std::string& message) { log("INFO", message); }
void Logger::error(const std::string& message) { log("ERROR", message); }
void Logger::warn(const std::string& message) { log("WARN", message); }
