#pragma once
#include <string>
#include <map>

class ConfigLoader {
public:
    bool load(const std::string& filename);
    std::string getVerifierMethodology() const;
    std::string get(const std::string& key, const std::string& defaultValue = "") const;

private:
    std::map<std::string, std::string> values;
};