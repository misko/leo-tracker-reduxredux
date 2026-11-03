#include "../../../native/adaptive/application/corrected_geometry.hpp"
#include <cassert>
#include <cstring>
#include <cstdio>
#include <limits>

using namespace leo::adaptive::application;

int main() {
    CorrectedGeometryProfile profile;
    profile.manifest_digest[0] = 7;
    profile.target_count = 1;
    profile.targets[0] = {3, 1000000000, {999687500.0, 999687500.0}, -2000000, 2000000};
    leo_scanner_visit_authority visit{};
    visit.abi_version = LEO_SCANNER_PROFILE_ABI_VERSION;
    visit.session = 1; visit.generation = 2; visit.visit = 3;
    visit.target_key = 3; visit.actual_frequency_hz = 1000000000;
    visit.sample_rate_hz = 7500000; visit.receiver_count = 2;
    visit.dwell_ms = 120; visit.probe_stride_ms = 120;
    visit.valid_start = 900000; visit.valid_end = 1800000;
    leo_scanner_detector_geometry full{}, repeat{};
    assert(derive_corrected_geometry(&profile, &visit, &full) == 0);
    assert(full.receiver_center_hz[0] == -312500);
    assert(full.receiver_center_hz[1] == -312500);
    assert(full.residual_cfo_min_hz == -800000 && full.residual_cfo_max_hz == 800000);
    assert(std::memcmp(full.profile_manifest_digest, profile.manifest_digest.data(), 32) == 0);
    assert(derive_corrected_geometry(&profile, &visit, &repeat) == 0);
    assert(std::memcmp(full.authority_digest, repeat.authority_digest, 32) == 0);
    ++visit.visit;
    assert(derive_corrected_geometry(&profile, &visit, &repeat) == 0);
    assert(std::memcmp(full.authority_digest, repeat.authority_digest, 32) != 0);
    --visit.visit;

    // Shared bounds must respect the more restricted receiver and analog bandwidth.
    profile.bandwidth_hz = 5000000;
    profile.targets[0].pilot_if_hz[1] = 999600000;
    assert(derive_corrected_geometry(&profile, &visit, &repeat) == 0);
    assert(repeat.residual_cfo_min_hz == -100000 && repeat.residual_cfo_max_hz == 100000);
    assert(repeat.receiver_center_hz[1] == -400000);
    profile.bandwidth_hz = 7500000;
    profile.targets[0].pilot_if_hz[1] = 999687500;

    const auto reject = [&](CorrectedGeometryProfile p, leo_scanner_visit_authority v) {
        leo_scanner_detector_geometry output{};
        output.probe_ms = 123;
        unsigned char before[sizeof(output)];
        std::memcpy(before, &output, sizeof(output));
        assert(derive_corrected_geometry(&p, &v, &output) != 0);
        assert(std::memcmp(before, &output, sizeof(output)) == 0);
    };
    auto p = profile; auto v = visit;
    p.targets[0].pilot_if_hz[0] = std::numeric_limits<double>::quiet_NaN(); reject(p, v);
    p = profile; p.targets[0].template_max_hz = std::numeric_limits<double>::infinity(); reject(p, v);
    p = profile; p.bandwidth_hz = 4000000; reject(p, v);
    p = profile; p.policy_half_width_hz = 800001; reject(p, v);
    p = profile; p.manifest_digest.fill(0); reject(p, v);
    p = profile; p.target_count = LEO_SCANNER_MAX_TARGETS + 1; reject(p, v);
    p = profile; v.actual_frequency_hz++; reject(p, v);
    v = visit; v.target_key++; reject(p, v);
    v = visit; v.valid_end--; reject(p, v);
    v = visit; v.probe_stride_ms = 20; reject(p, v);
    v = visit; v.receiver_count = 1; reject(p, v);
    v = visit; v.sample_rate_hz = 2500000; reject(p, v);
    assert(derive_corrected_geometry(nullptr, &visit, &repeat) != 0);
    assert(derive_corrected_geometry(&profile, nullptr, &repeat) != 0);
    assert(derive_corrected_geometry(&profile, &visit, nullptr) != 0);
    for (auto byte : full.authority_digest) std::printf("%02x", byte);
    std::puts("");
}
