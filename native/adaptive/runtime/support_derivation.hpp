#pragma once

#include "runtime.hpp"

#include <array>
#include <cstdint>
#include <string>
#include <string_view>

namespace leo::adaptive {

// Value returned by an explicitly selected support-authority profile. Numeric
// support and authority lexemes travel together so callers cannot derive one
// profile's geometry and serialize it with another profile's spelling.
struct SupportDerivation {
    Support numeric{};
    std::array<std::string, 4> factorial_moment_lexemes;
};

enum class SupportDerivationStatus {
    ok,
    invalid_input,
    unavailable,
};

struct SupportProfileBinding {
    std::string profile_name;
    std::string profile_manifest_digest;
};

using SupportDeriveFunction = SupportDerivationStatus (*)(
    void* context,
    std::uint32_t rate,
    std::uint32_t probe_samples,
    std::int64_t integer_epoch,
    double fractional_offset,
    SupportDerivation* output);

// Synchronous borrowed port. The profile binding is a caller attestation: a
// generic consumer can validate and copy its spelling, but cannot prove that a
// callback/context implements that profile. A profile-owned adapter should
// therefore supply all four fields together. The binding views need remain
// valid only while a session copies them at construction. Context and callback
// remain valid until that session is destroyed, after all producer calls have
// stopped. A caller serializes calls to one context; separate contexts may
// execute concurrently. The callback returns status and must not allow
// exceptions to cross the port.
struct SupportDerivationPort {
    void* context{};
    std::string_view profile_name;
    std::string_view profile_manifest_digest;
    SupportDeriveFunction derive{};
};

}  // namespace leo::adaptive
