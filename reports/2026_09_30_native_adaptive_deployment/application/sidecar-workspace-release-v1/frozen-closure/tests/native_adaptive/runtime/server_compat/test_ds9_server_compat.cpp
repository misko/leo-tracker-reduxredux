#include "server_compat.hpp"

#include <cassert>
#include <cfenv>
#include <clocale>
#include <cmath>
#include <cstdlib>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
std::vector<std::string> fields(const std::string& line) {
    std::vector<std::string> output;
    std::size_t begin = 0;
    for (;;) {
        const auto end = line.find('\t', begin);
        output.push_back(line.substr(begin, end - begin));
        if (end == std::string::npos) return output;
        begin = end + 1;
    }
}
template <typename T> T integer(const std::string& text) {
    char* end = nullptr;
    const long long value = std::strtoll(text.c_str(), &end, 10);
    if (end != text.c_str() + text.size() ||
        value < static_cast<long long>(std::numeric_limits<T>::min()) ||
        value > static_cast<long long>(std::numeric_limits<T>::max())) {
        throw std::runtime_error("invalid integer");
    }
    return static_cast<T>(value);
}
double number(const std::string& text) {
    char* end = nullptr;
    const double value = std::strtod(text.c_str(), &end);
    if (end != text.c_str() + text.size() || !std::isfinite(value)) {
        throw std::runtime_error("invalid number");
    }
    return value;
}
std::uint64_t bits(double value) {
    std::uint64_t output = 0;
    std::memcpy(&output, &value, sizeof(output));
    return output;
}
}

int main(int argc, char** argv) {
    try {
        if (argc != 4) throw std::runtime_error("usage: test-ds9 INPUT EXPECTED LEXEMES");
        if (std::setlocale(LC_NUMERIC, "C") == nullptr ||
            std::fesetround(FE_TONEAREST) != 0) throw std::runtime_error("environment");
        std::ifstream inputs(argv[1]), expected(argv[2]), lexemes(argv[3]);
        if (!inputs || !expected || !lexemes) throw std::runtime_error("cannot open fixture");
        leo::adaptive::server_compat::SupportDeriver deriver(
            leo::adaptive::server_compat::authority_binding());
        std::size_t rows = 0, retained = 0;
        std::string input_line, expected_line, lexeme_line;
        while (std::getline(inputs, input_line)) {
            if (!std::getline(expected, expected_line) || !std::getline(lexemes, lexeme_line)) {
                throw std::runtime_error("truncated fixture");
            }
            ++rows;
            if (expected_line == "unavailable") {
                if (lexeme_line != "unavailable") throw std::runtime_error("retention mismatch");
                continue;
            }
            const auto input = fields(input_line);
            const auto oracle = fields(expected_line);
            const auto authority = fields(lexeme_line);
            if (input.size() != 23 || oracle.size() != 9 || authority.size() != 3 ||
                oracle[0] != authority[0]) throw std::runtime_error("invalid fixture row");
            const auto rate = integer<std::uint32_t>(input[0]);
            const auto support = deriver.derive(
                rate, rate / 50, integer<std::int64_t>(input[16]), number(input[17]));
            const auto start = leo::adaptive::support_utc_ns(
                std::stoull(input[1]), std::stoll(input[2]), std::stoull(input[5]),
                support.numeric.first, rate);
            const auto center = leo::adaptive::support_utc_ns(
                std::stoull(input[1]), std::stoll(input[2]), std::stoull(input[5]),
                support.numeric.center, rate);
            const auto end = leo::adaptive::support_utc_ns(
                std::stoull(input[1]), std::stoll(input[2]), std::stoull(input[5]),
                support.numeric.end, rate);
            if (start != std::stoll(oracle[2]) || center != std::stoll(oracle[3]) ||
                end != std::stoll(oracle[4]) ||
                bits(support.numeric.moment2) != bits(number(oracle[7])) ||
                bits(support.numeric.moment3) != bits(number(oracle[8])) ||
                support.factorial_moment_lexemes[2] != authority[1] ||
                support.factorial_moment_lexemes[3] != authority[2]) {
                throw std::runtime_error("DS9 server support mismatch");
            }
            ++retained;
        }
        if (std::getline(expected, expected_line) || std::getline(lexemes, lexeme_line) ||
            rows != 24'681 || retained != 11'747) throw std::runtime_error("fixture cardinality");
        const auto stats = deriver.cache_stats();
        if (stats.hits != 2'237 || stats.misses != 9'510 || !stats.populated) {
            throw std::runtime_error("cache accounting mismatch");
        }
        std::cout << "server compatibility DS9: 11747 retained exact; cache 2237 hits, "
                     "9510 misses\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
