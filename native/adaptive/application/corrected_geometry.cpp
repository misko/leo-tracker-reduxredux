#include "corrected_geometry.hpp"
#include "../runtime/sha256.hpp"
#include <algorithm>
#include <cerrno>
#include <cmath>
#include <cstring>
#include <limits>
#include <string>

namespace leo::adaptive::application {
namespace {
void append_u64(std::string& out, std::uint64_t value) {
    for (unsigned i = 0; i < 8; ++i)
        out.push_back(static_cast<char>((value >> (8 * i)) & 255));
}
void append_double(std::string& out, double value) {
    static_assert(sizeof(double) == sizeof(std::uint64_t), "binary64 required");
    static_assert(std::numeric_limits<double>::is_iec559, "IEEE-754 required");
    std::uint64_t bits;
    std::memcpy(&bits, &value, sizeof(bits));
    append_u64(out, bits);
}
unsigned nibble(char c) {
    return c <= '9' ? static_cast<unsigned>(c - '0') :
        static_cast<unsigned>(c - 'a' + 10);
}
}

int derive_corrected_geometry(void* context,
        const leo_scanner_visit_authority* visit,
        leo_scanner_detector_geometry* output) {
    if (!context || !visit || !output) return -EINVAL;
    const auto& profile = *static_cast<const CorrectedGeometryProfile*>(context);
    if (visit->abi_version != LEO_SCANNER_PROFILE_ABI_VERSION ||
        profile.sample_rate_hz != 7500000 ||
        visit->sample_rate_hz != profile.sample_rate_hz ||
        visit->receiver_count != 2 || visit->probe_stride_ms != 120 ||
        !profile.bandwidth_hz || !profile.target_count ||
        profile.target_count > profile.targets.size() ||
        visit->target_index >= profile.target_count ||
        !std::isfinite(profile.policy_half_width_hz) ||
        profile.policy_half_width_hz <= 0 || profile.policy_half_width_hz > 800000 ||
        !std::any_of(profile.manifest_digest.begin(), profile.manifest_digest.end(),
                     [](std::uint8_t value) { return value != 0; }) ||
        (visit->dwell_ms != 120 && visit->dwell_ms != 240 && visit->dwell_ms != 360) ||
        visit->valid_end < visit->valid_start ||
        visit->valid_end - visit->valid_start !=
            static_cast<std::uint64_t>(profile.sample_rate_hz) * visit->dwell_ms / 1000)
        return -EINVAL;
    const auto& target = profile.targets[visit->target_index];
    if (!target.tuned_if_hz || target.tuned_if_hz > UINT64_C(9007199254740992) ||
        target.target_key != visit->target_key ||
        target.tuned_if_hz != visit->actual_frequency_hz ||
        !std::isfinite(target.template_min_hz) ||
        !std::isfinite(target.template_max_hz) ||
        target.template_min_hz >= target.template_max_hz)
        return -EINVAL;
    leo_scanner_detector_geometry geometry{};
    geometry.abi_version = LEO_SCANNER_PROFILE_ABI_VERSION;
    geometry.sample_rate_hz = profile.sample_rate_hz;
    geometry.receiver_count = 2;
    geometry.probe_ms = 20;
    geometry.probe_stride_ms = 120;
    std::copy(profile.manifest_digest.begin(), profile.manifest_digest.end(),
              geometry.profile_manifest_digest);
    const double usable = std::min(profile.sample_rate_hz, profile.bandwidth_hz) / 2.0;
    double width = profile.policy_half_width_hz;
    for (unsigned receiver = 0; receiver < 2; ++receiver) {
        const double center = target.pilot_if_hz[receiver] - target.tuned_if_hz;
        const double observable = std::min(center + target.template_min_hz + usable,
                                          usable - center - target.template_max_hz);
        if (!std::isfinite(center) || !std::isfinite(observable) || observable <= 0)
            return -ERANGE;
        geometry.receiver_center_hz[receiver] = center;
        width = std::min(width, observable);
    }
    geometry.residual_cfo_min_hz = -width;
    geometry.residual_cfo_max_hz = width;
    try {
        std::string material("leo-corrected-visit-geometry/v1");
        material.push_back('\0');
        material.append(reinterpret_cast<const char*>(profile.manifest_digest.data()), 32);
        for (std::uint64_t value : {visit->session, visit->generation, visit->visit,
             visit->actual_frequency_hz, visit->selection_counter,
             visit->transition_previous_valid_end, visit->transition_valid_start,
             visit->valid_start, visit->valid_end}) append_u64(material, value);
        for (std::uint32_t value : {visit->target_index, visit->target_key,
             visit->profile_crc32, visit->transition_flags, visit->sample_rate_hz,
             visit->receiver_count, visit->dwell_ms, visit->probe_stride_ms,
             profile.bandwidth_hz}) append_u64(material, value);
        for (double value : {target.pilot_if_hz[0], target.pilot_if_hz[1],
             target.template_min_hz, target.template_max_hz,
             profile.policy_half_width_hz, geometry.receiver_center_hz[0],
             geometry.receiver_center_hz[1], -width, width}) append_double(material, value);
        const auto hex = leo::adaptive::sha256(material);
        for (unsigned i = 0; i < 32; ++i)
            geometry.authority_digest[i] = static_cast<std::uint8_t>(
                (nibble(hex[2 * i]) << 4) | nibble(hex[2 * i + 1]));
    } catch (...) { return -ENOMEM; }
    *output = geometry;
    return 0;
}
}
