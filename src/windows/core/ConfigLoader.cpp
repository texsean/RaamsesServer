/**
 * RGS Windows Core — ConfigLoader stub
 *
 * Windows implementation of configuration loading.
 * Reads from INI/JSON config files (portable cross-platform).
 */

#include "ConfigLoader.h"
#include <fstream>
#include <string>

namespace rgs {

bool ConfigLoader::load(const std::string& filename) {
    std::ifstream file(filename);
    if (!file.is_open()) {
        return false;
    }

    // Parse config file
    std::string line;
    while (std::getline(file, line)) {
        if (line.empty() || line[0] == '#' || line[0] == ';') {
            continue;  // skip comments
        }
        auto eq = line.find('=');
        if (eq != std::string::npos) {
            std::string key = line.substr(0, eq);
            std::string value = line.substr(eq + 1);
            // Trim whitespace
            key.erase(0, key.find_first_not_of(" \t"));
            key.erase(key.find_last_not_of(" \t") + 1);
            value.erase(0, value.find_first_not_of(" \t"));
            value.erase(value.find_last_not_of(" \t") + 1);
            _config[key] = value;
        }
    }

    return !_config.empty();
}

std::string ConfigLoader::get(const std::string& key, const std::string& default_value) const {
    auto it = _config.find(key);
    if (it != _config.end()) {
        return it->second;
    }
    return default_value;
}

int ConfigLoader::get_int(const std::string& key, int default_value) const {
    auto val = get(key, std::to_string(default_value));
    try {
        return std::stoi(val);
    } catch (...) {
        return default_value;
    }
}

} // namespace rgs
