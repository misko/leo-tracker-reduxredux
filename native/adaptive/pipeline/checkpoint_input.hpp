#pragma once
#include "pipeline.hpp"
#include <istream>
#include <cerrno>
#include <cmath>
#include <cstdlib>
#include <limits>
#include <stdexcept>

namespace leo::adaptive::pipeline::checkpoint {
inline std::vector<std::string> fields(const std::string& line) {
    std::vector<std::string> result;
    std::size_t start=0;
    while (true) {
        const auto end=line.find('\t',start);
        result.push_back(line.substr(start,end-start));
        if (end==std::string::npos) return result;
        start=end+1;
    }
}

template <typename T> T integer(const std::string& text) {
    errno=0;char* end=nullptr;const long long value=std::strtoll(text.c_str(),&end,10);
    if (errno || text.empty() || end!=text.c_str()+text.size() ||
        value<static_cast<long long>(std::numeric_limits<T>::min()) ||
        value>static_cast<long long>(std::numeric_limits<T>::max()))
        throw std::runtime_error("invalid integer field");
    return static_cast<T>(value);
}

inline double real(const std::string& text) {
    errno=0;char* end=nullptr;const double value=std::strtod(text.c_str(),&end);
    if (errno || text.empty() || end!=text.c_str()+text.size() || !std::isfinite(value)) throw std::runtime_error("invalid real field");
    return value;
}

inline std::vector<leo::adaptive::tracking::Candidate> read_candidates(std::istream& input) {
    std::string line;if(!std::getline(input,line))throw std::runtime_error("empty candidates");
    std::vector<leo::adaptive::tracking::Candidate> output;
    while(std::getline(input,line)) {
        if(line.empty()) continue;
        const auto f=fields(line);
        if(f.size()!=13)throw std::runtime_error("invalid candidate row");
        output.push_back({f[0],f[1],integer<int>(f[2]),integer<int>(f[3]),f[4],real(f[5]),
            integer<std::int64_t>(f[6]),integer<std::int64_t>(f[7]),integer<std::int64_t>(f[8]),
            real(f[9]),real(f[10]),real(f[11]),real(f[12])});
    }
    if(input.bad() || !input.eof())throw std::runtime_error("candidate input read failed");
    return output;
}

inline leo::adaptive::pipeline::GraphAuthority read_authority(std::istream& input) {
    std::string line;if(!std::getline(input,line))throw std::runtime_error("empty graph authority");
    const auto meta=fields(line);if(meta.size()!=4 || meta[0]!="META")
        throw std::runtime_error("invalid graph metadata");
    leo::adaptive::pipeline::GraphAuthority output{meta[1],meta[2],integer<std::int64_t>(meta[3]),{}};
    if(!std::getline(input,line))throw std::runtime_error("missing graph header");
    while(std::getline(input,line)) {
        if(line.empty()) continue;
        const auto f=fields(line);
        if(f.size()!=8)throw std::runtime_error("invalid graph authority row");
        const bool inserted=output.candidates.emplace(f[0],leo::adaptive::pipeline::SupportAuthority{
            integer<std::int64_t>(f[1]),integer<std::int64_t>(f[2]),integer<std::int64_t>(f[3]),
            f[4],f[5],f[6],f[7]}).second;
        if(!inserted)throw std::runtime_error("duplicate graph candidate");
    }
    if(input.bad() || !input.eof())throw std::runtime_error("authority input read failed");
    return output;
}
}
