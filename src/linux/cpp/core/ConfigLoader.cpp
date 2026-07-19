#include "ConfigLoader.h"
#include <fstream>
#include <sstream>
#include <algorithm>

bool ConfigLoader::load(const std::string& filename) {
    std::ifstream file(filename);
    if (!file.is_open()) return false;

    std::string line;
    while (std::getline(file, line)) {
        // Skip comments and empty lines
        if (line.empty() || line[0] == '#') continue;

        size_t eq = line.find('=');
        if (eq == std::string::npos) continue;

        std::string key = line.substr(0, eq);
        std::string value = line.substr(eq + 1);

        // Trim whitespace
        key.erase(std::remove_if(key.begin(), key.end(), ::isspace), key.end());
        value.erase(0, value.find_first_not_of(" \t"));
        value.erase(value.find_last_not_of(" \t") + 1);

        values[key] = value;
    }
    return true;
}

std::string ConfigLoader::getVerifierMethodology() const {
    return get("inactivity_methodology", "auto");
}

std::string ConfigLoader::get(const std::string& key, const std::string& defaultValue) const {
    auto it = values.find(key);
    return (it != values.end()) ? it->second : defaultValue;
}
