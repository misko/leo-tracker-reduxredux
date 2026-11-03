#include "python_float_repr_compat.hpp"

#include <cerrno>
#include <cfenv>
#include <clocale>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace {

std::vector<std::string> fields(const std::string& line) {
    std::vector<std::string> output;
    std::size_t begin = 0;
    for (;;) {
        const std::size_t end = line.find('\t', begin);
        output.push_back(line.substr(begin, end - begin));
        if (end == std::string::npos) return output;
        begin = end + 1;
    }
}

double number(const std::string& text) {
    errno = 0;
    char* end = nullptr;
    const double value = std::strtod(text.c_str(), &end);
    if (errno != 0 || end != text.c_str() + text.size() || !std::isfinite(value)) {
        throw std::runtime_error("invalid finite binary64 input");
    }
    return value;
}

std::string max_digits10(double value) {
    std::ostringstream output;
    output << std::setprecision(std::numeric_limits<double>::max_digits10) << value;
    return output.str();
}

void require_example(double value, const std::string& expected) {
    const auto actual = leo::adaptive::research::server_python_float_repr_compat(value);
    if (actual != expected) {
        throw std::runtime_error("Python compatibility edge example differs");
    }
}

}  // namespace

int main(int argc, char** argv) {
    try {
        if (argc != 3) {
            throw std::runtime_error("usage: test-python-float-repr EXPECTED.tsv LEXEMES.tsv");
        }
        if (std::setlocale(LC_NUMERIC, "C") == nullptr ||
            std::fesetround(FE_TONEAREST) != 0) {
            throw std::runtime_error("cannot establish formatter environment");
        }
        require_example(0.0, "0.0");
        require_example(-0.0, "-0.0");
        require_example(1.0, "1.0");
        require_example(1.0e-4, "0.0001");
        require_example(1.0e-5, "1e-05");
        require_example(1.0e15, "1000000000000000.0");
        require_example(1.0e16, "1e+16");
        require_example(std::ldexp(1.0, -1017), "7.120236347223045e-307");
        bool rejected_nonfinite = false;
        try {
            (void)leo::adaptive::research::server_python_float_repr_compat(
                std::numeric_limits<double>::infinity());
        } catch (const std::invalid_argument&) {
            rejected_nonfinite = true;
        }
        if (!rejected_nonfinite) throw std::runtime_error("nonfinite value accepted");
        if (std::fesetround(FE_DOWNWARD) != 0) {
            throw std::runtime_error("cannot exercise non-nearest rounding rejection");
        }
        bool rejected_rounding = false;
        try {
            (void)leo::adaptive::research::server_python_float_repr_compat(1.25);
        } catch (const std::invalid_argument&) {
            rejected_rounding = true;
        }
        if (std::fesetround(FE_TONEAREST) != 0 || !rejected_rounding) {
            throw std::runtime_error("non-nearest rounding mode accepted");
        }

        std::ifstream values(argv[1]);
        std::ifstream lexemes(argv[2]);
        if (!values || !lexemes) throw std::runtime_error("cannot open corpus inputs");
        std::size_t rows = 0;
        std::size_t retained = 0;
        std::size_t values_checked = 0;
        std::size_t zero_values = 0;
        std::size_t compatibility_mismatches = 0;
        std::size_t max_digits_moment2_mismatches = 0;
        std::size_t max_digits_moment3_mismatches = 0;
        std::string value_line;
        std::string lexeme_line;
        while (std::getline(values, value_line)) {
            if (!std::getline(lexemes, lexeme_line)) {
                throw std::runtime_error("lexeme corpus is truncated");
            }
            ++rows;
            if (value_line == "unavailable" || lexeme_line == "unavailable") {
                if (value_line != lexeme_line) {
                    throw std::runtime_error("retention mismatch");
                }
                continue;
            }
            const auto input = fields(value_line);
            const auto expected = fields(lexeme_line);
            if (input.size() != 9 || expected.size() != 3 || input[0] != expected[0]) {
                throw std::runtime_error("corpus identity mismatch");
            }
            ++retained;
            const double moment2 = number(input[7]);
            const double moment3 = number(input[8]);
            const std::string actual2 =
                leo::adaptive::research::server_python_float_repr_compat(moment2);
            const std::string actual3 =
                leo::adaptive::research::server_python_float_repr_compat(moment3);
            compatibility_mismatches += actual2 != expected[1];
            compatibility_mismatches += actual3 != expected[2];
            max_digits_moment2_mismatches += max_digits10(moment2) != expected[1];
            max_digits_moment3_mismatches += max_digits10(moment3) != expected[2];
            zero_values += moment2 == 0.0;
            zero_values += moment3 == 0.0;
            values_checked += 2;
        }
        if (std::getline(lexemes, lexeme_line)) {
            throw std::runtime_error("lexeme corpus has extra rows");
        }
        if (rows != 24'681 || retained != 11'747 || values_checked != 23'494 ||
            zero_values != 1'949 || compatibility_mismatches != 0 ||
            max_digits_moment2_mismatches != 5'987 ||
            max_digits_moment3_mismatches != 6'588) {
            throw std::runtime_error("corpus result differs from frozen DS9 evidence");
        }
        std::cout << "server Python float repr compatibility: " << retained
                  << " retained rows, " << values_checked << " moment values exact; "
                  << zero_values << " Python 0.0 spellings repaired\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
