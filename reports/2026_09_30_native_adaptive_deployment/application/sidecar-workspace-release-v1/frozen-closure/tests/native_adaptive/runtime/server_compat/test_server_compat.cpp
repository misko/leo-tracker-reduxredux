#include "server_compat.hpp"

#include <cassert>
#include <cfenv>
#include <clocale>
#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <string>

using namespace leo::adaptive;
using namespace leo::adaptive::server_compat;

namespace {
std::uint64_t bits(double value) {
    std::uint64_t output = 0;
    std::memcpy(&output, &value, sizeof(output));
    return output;
}
}

int main() {
    assert(std::setlocale(LC_NUMERIC, "C") != nullptr);
    assert(std::fesetround(FE_TONEAREST) == 0);
    const std::string numeric_locale = std::setlocale(LC_NUMERIC, nullptr);
    bool rejected = false;
    try {
        (void)SupportDeriver({"portable-v1", kProfileManifestDigest});
    } catch (const std::invalid_argument&) {
        rejected = true;
    }
    assert(rejected);

    assert(std::fesetround(FE_DOWNWARD) == 0);
    rejected = false;
    try {
        (void)SupportDeriver(authority_binding());
    } catch (const std::invalid_argument&) {
        rejected = true;
    }
    assert(rejected);
    assert(std::fesetround(FE_TONEAREST) == 0);
    rejected = false;
    try {
        (void)SupportDeriver({kProfileName, "sha256:bad"});
    } catch (const std::invalid_argument&) {
        rejected = true;
    }
    assert(rejected);

    // Linking the opt-in module does not alter the portable default.
    const auto portable = fractional_support(2'500'000, 50'000, 100, 0.25);
    assert(bits(portable.moment2) == UINT64_C(0x3ef166f15ab86ced));
    assert(bits(portable.moment3) == UINT64_C(0x3d263e0245b216c1));

    SupportDeriver deriver(authority_binding());
    assert(deriver.binding().profile_name == kProfileName);
    assert(deriver.binding().profile_manifest_digest == kProfileManifestDigest);
    const auto first = deriver.derive(2'500'000, 50'000, 100, 0.25);
    assert(!first.cache_hit && first.factorial_moment_lexemes[0] == "1.0" &&
        first.factorial_moment_lexemes[1] == "0.0");
    const auto second = deriver.derive(2'500'000, 50'000, 100, 0.25);
    assert(second.cache_hit && bits(first.numeric.moment2) == bits(second.numeric.moment2) &&
        bits(first.numeric.moment3) == bits(second.numeric.moment3) &&
        first.factorial_moment_lexemes == second.factorial_moment_lexemes);
    auto stats = deriver.cache_stats();
    assert(stats.hits == 1 && stats.misses == 1 && stats.populated);

    rejected = false;
    try {
        (void)deriver.derive(0, 50'000, 100, 0.25);
    } catch (const std::invalid_argument&) {
        rejected = true;
    }
    assert(rejected);
    const auto after_failure = deriver.derive(2'500'000, 50'000, 100, 0.25);
    assert(after_failure.cache_hit);
    stats = deriver.cache_stats();
    assert(stats.hits == 2 && stats.misses == 2 && stats.populated);

    assert(std::fesetround(FE_DOWNWARD) == 0);
    rejected = false;
    try {
        (void)deriver.derive(2'500'000, 50'000, 100, 0.25);
    } catch (const std::invalid_argument&) {
        rejected = true;
    }
    assert(rejected);
    assert(std::fesetround(FE_TONEAREST) == 0);
    assert(std::string(std::setlocale(LC_NUMERIC, nullptr)) == numeric_locale);
    stats = deriver.cache_stats();
    assert(stats.hits == 2 && stats.misses == 2 && stats.populated);
    deriver.clear_cache();
    assert(!deriver.cache_stats().populated);

    SupportDeriver port_owner(authority_binding());
    const auto port=derivation_port(port_owner);
    assert(port.context==&port_owner && port.derive &&
        port.profile_name==kProfileName &&
        port.profile_manifest_digest==kProfileManifestDigest);
    leo::adaptive::SupportDerivation neutral;
    assert(port.derive(port.context,2'500'000,50'000,100,0.25,&neutral)==
        SupportDerivationStatus::ok);
    assert(bits(neutral.numeric.moment2)==bits(first.numeric.moment2) &&
        bits(neutral.numeric.moment3)==bits(first.numeric.moment3) &&
        neutral.factorial_moment_lexemes==first.factorial_moment_lexemes);
    assert(port.derive(nullptr,2'500'000,50'000,100,0.25,&neutral)==
        SupportDerivationStatus::invalid_input);
}
