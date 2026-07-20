#pragma once

#include <string>
#include <map>

namespace rgs {

/**
 * Loads and parses configuration from a text file.
 * Supports key=value format with # and ; comments.
 */
class ConfigLoader {
public:
    bool load(const std::string& filename);
    std::string get(const std::string& key, const std::string& default_value = "") const;
    int get_int(const std::string& key, int default_value = 0) const;

private:
    std::map<std::string, std::string> _config;
};

} // namespace rgs
