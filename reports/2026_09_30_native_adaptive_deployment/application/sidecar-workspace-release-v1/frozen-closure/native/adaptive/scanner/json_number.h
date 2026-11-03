#ifndef LEO_ADAPTIVE_SCANNER_JSON_NUMBER_H
#define LEO_ADAPTIVE_SCANNER_JSON_NUMBER_H

#include <cmath>
#include <cstdio>

inline void leo_scanner_json_number(FILE* stream, double value)
{
    if (std::isfinite(value))
        std::fprintf(stream, "%.17g", value);
    else
        std::fputs("null", stream);
}

#endif
