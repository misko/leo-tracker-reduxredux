#pragma once
#include "location.h"
#include "tle_id.hpp"
#include <cerrno>
#include <cstdlib>
#include <cstring>
#include <istream>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

namespace leo::adaptive::location {
// Explicit counted catalogue checkpoint. Eligibility and capture binding are
// the caller's responsibility; identities, lengths and order are validated here.
inline std::vector<leo_tle_record> read_tle_records(std::istream& input) {
    std::string line;
    if(!std::getline(input,line))throw std::invalid_argument("missing TLE count");
    errno=0;char* end=nullptr;const long long count=std::strtoll(line.c_str(),&end,10);
    if(errno || line.empty() || *end || count<1 || count>20000)
        throw std::invalid_argument("invalid TLE count");
    std::vector<leo_tle_record> records(static_cast<size_t>(count));std::set<int> ids;
    for(auto& record:records) {
        std::string a,b;
        if(!std::getline(input,a) || !std::getline(input,b) || a.size()!=69 || b.size()!=69)
            throw std::invalid_argument("invalid TLE line length");
        int32_t first=0,second=0;
        if(!parse_tle_catalogue_id(std::string_view(a).substr(2,5),first) ||
           !parse_tle_catalogue_id(std::string_view(b).substr(2,5),second) ||
           first!=second || !ids.insert(first).second)
            throw std::invalid_argument("invalid or duplicate TLE identity");
        record.satellite_id=first;
        std::memcpy(record.line1,a.c_str(),70);std::memcpy(record.line2,b.c_str(),70);
    }
    if(std::getline(input,line))throw std::invalid_argument("trailing TLE rows");
    if(input.bad() || !input.eof())throw std::runtime_error("TLE input read failed");
    return records;
}
}
