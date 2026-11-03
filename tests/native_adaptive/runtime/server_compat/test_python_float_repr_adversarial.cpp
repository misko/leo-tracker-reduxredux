#include "python_float_repr.hpp"

#include <cfenv>
#include <clocale>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>

int main(int argc, char** argv) {
    try {
        if (argc != 2) throw std::runtime_error("usage: test-python-repr-adversarial CASES.tsv");
        if (std::setlocale(LC_NUMERIC, "C") == nullptr ||
            std::fesetround(FE_TONEAREST) != 0) {
            throw std::runtime_error("cannot establish formatter environment");
        }
        std::ifstream input(argv[1]);
        if (!input) throw std::runtime_error("cannot open adversarial cases");
        std::size_t count = 0;
        std::string line;
        while (std::getline(input, line)) {
            const std::size_t separator = line.find('\t');
            if (separator != 16 || line.find('\t', separator + 1) != std::string::npos) {
                throw std::runtime_error("invalid adversarial row");
            }
            std::size_t consumed = 0;
            const std::uint64_t bits = std::stoull(line.substr(0, separator), &consumed, 16);
            if (consumed != separator) throw std::runtime_error("invalid binary64 bits");
            double value = 0.0;
            static_assert(sizeof(value) == sizeof(bits), "binary64 required");
            std::memcpy(&value, &bits, sizeof(value));
            const std::string expected = line.substr(separator + 1);
            const std::string actual =
                leo::adaptive::server_compat::detail::python_float_repr(value);
            if (actual != expected) {
                throw std::runtime_error("Python repr mismatch at row " +
                    std::to_string(count + 1));
            }
            ++count;
        }
        if (count < 100'000 || count > 120'000) {
            throw std::runtime_error("unexpected adversarial corpus cardinality");
        }
        std::cout << "server Python float repr adversarial: " << count
                  << " unique finite binary64 values exact\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
