#pragma once
#include <string>

class Logger {
public:
    static void init(const std::string& logFile);
    static void info(const std::string& message);
    static void error(const std::string& message);
    static void warn(const std::string& message);
};