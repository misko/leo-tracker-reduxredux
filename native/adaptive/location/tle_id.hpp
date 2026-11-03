#pragma once
#include <cstdint>
#include <string_view>

namespace leo::adaptive::location {
// Fixed-width catalogue identifier in TLE columns 3-7. Alpha-5 omits I/O.
// These are actual catalogue numbers, never positions in a filtered array.
// Failure leaves the output unchanged.
inline bool parse_tle_catalogue_id(std::string_view field,std::int32_t& output) {
    if(field.size()!=5) return false;
    std::size_t index=0;std::int32_t value=0;
    if(field[0]>='A' && field[0]<='Z') {
        constexpr std::string_view alphabet="ABCDEFGHJKLMNPQRSTUVWXYZ";
        const auto prefix=alphabet.find(field[0]);
        if(prefix==std::string_view::npos) return false;
        value=static_cast<std::int32_t>(prefix)+10;index=1;
    } else {
        while(index<field.size() && field[index]==' ') ++index;
        if(index==field.size()) return false;
    }
    for(;index<field.size();++index) {
        const char digit=field[index];
        if(digit<'0' || digit>'9') return false;
        value=value*10+(digit-'0');
    }
    if(value<=0) return false;
    output=value;return true;
}
}
