#include "python_float_repr_compat.hpp"

#include <cfenv>
#include <clocale>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <iostream>
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
    char* end = nullptr;
    const double value = std::strtod(text.c_str(), &end);
    if (end != text.c_str() + text.size() || !std::isfinite(value)) {
        throw std::runtime_error("invalid finite moment");
    }
    return value;
}

}  // namespace

int main(int argc, char** argv) {
    try {
        if (argc != 4) {
            throw std::runtime_error(
                "usage: build-server-graph-compat ORIGINAL-GRAPH.tsv MOMENTS.tsv OUTPUT.tsv");
        }
        if (std::setlocale(LC_NUMERIC, "C") == nullptr ||
            std::fesetround(FE_TONEAREST) != 0) {
            throw std::runtime_error("cannot establish formatter environment");
        }
        std::ifstream original(argv[1]);
        std::ifstream moments(argv[2]);
        std::ofstream output(argv[3]);
        if (!original || !moments || !output) throw std::runtime_error("cannot open graph input");
        std::string metadata;
        std::string header;
        if (!std::getline(original, metadata) || metadata.compare(0, 5, "META\t") != 0 ||
            !std::getline(original, header) || header.compare(0, 13, "candidate_id\t") != 0) {
            throw std::runtime_error("invalid original graph header");
        }
        output << metadata << '\n' << header << '\n';
        std::size_t rows = 0;
        std::size_t retained = 0;
        std::string line;
        while (std::getline(moments, line)) {
            ++rows;
            if (line == "unavailable") continue;
            const auto item = fields(line);
            if (item.size() != 9) throw std::runtime_error("invalid recomputed moment row");
            output << item[0] << '\t' << item[2] << '\t' << item[3] << '\t' << item[4]
                   << "\t1.0\t0.0\t"
                   << leo::adaptive::research::server_python_float_repr_compat(number(item[7]))
                   << '\t'
                   << leo::adaptive::research::server_python_float_repr_compat(number(item[8]))
                   << '\n';
            ++retained;
        }
        if (rows != 24'681 || retained != 11'747 || !output) {
            throw std::runtime_error("unexpected graph cardinality or output failure");
        }
        std::cout << "recomputed server graph: " << retained << " candidates\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
