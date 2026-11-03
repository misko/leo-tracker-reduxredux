#include "recorded_main.hpp"

#include <cassert>
#include <string>
#include <vector>

namespace {
int invoke(std::vector<std::string> arguments) {
    std::vector<char*> values;
    values.reserve(arguments.size());
    for (auto& argument : arguments) values.push_back(argument.data());
    return leo::adaptive::application::recorded::run_cli(
        static_cast<int>(values.size()), values.data());
}

std::vector<std::string> valid_shape(const std::string& output) {
    return {"test-recorded-application", "--bundle-native", "/missing/native.tsv",
        "--bundle-sha256", std::string(64, 'a'), "--analysis-digest",
        "sha256:" + std::string(64, 'b'), "--exact-template", "/missing/exact",
        "--control-template", "/missing/control", "--tle-catalogue", "/missing/tles",
        "--search-origin", "38", "-122", "--search-radius-km", "1",
        "--search-region-km", "2", "--search-level-km", "2",
        "--search-point-budget", "1", "--search-slice-points", "1",
        "--wall-seconds", "60", "--detector-workers", "1",
        "--analysis-workers", "1", "--output", output};
}
}

int main(int argc, char** argv) {
    assert(argc == 2);
    assert(invoke({"test-recorded-application"}) == 1);
    // Existing destinations fail before opening any scientific input.
    assert(invoke(valid_shape(argv[1])) == 1);
    // Output below the read-only public store is rejected before input access.
    assert(invoke(valid_shape("/mnt/qnap01/forbidden-recorded-output")) == 1);
    auto invalid_workers = valid_shape(std::string(argv[1]) + "/child");
    invalid_workers[invalid_workers.size() - 5U] = "2"; // detector-workers value
    assert(invoke(std::move(invalid_workers)) == 1);
    return 0;
}
