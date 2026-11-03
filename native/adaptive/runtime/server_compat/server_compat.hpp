#pragma once

#include "runtime.hpp"
#include "support_derivation.hpp"

#include <array>
#include <cstdint>
#include <memory>
#include <string>

namespace leo::adaptive::server_compat {

inline constexpr const char* kProfileName =
    "server-x86_64-glibc-2.43-fma-python-repr-v1";
inline constexpr const char* kProfileManifestDigest =
    "sha256:3847a5318ae80414d6cff060f04d305363e95bb6c86dbfbe9faca45f42b40cb5";

struct AuthorityBinding {
    std::string profile_name;
    std::string profile_manifest_digest;
};

AuthorityBinding authority_binding();

struct DerivedSupport {
    Support numeric{};
    std::array<std::string, 4> factorial_moment_lexemes;
    bool cache_hit{};
};

struct CacheStats {
    std::uint64_t hits{};
    std::uint64_t misses{};
    bool populated{};
};

// Explicit server-authority compatibility profile. Each instance is bound to
// one named profile/manifest and owns one successful exact cache entry. Calls
// on the same instance are synchronous and single-owner; independent instances
// may be used concurrently. The class never changes locale or FP rounding.
class SupportDeriver {
public:
    explicit SupportDeriver(AuthorityBinding binding);
    ~SupportDeriver();
    SupportDeriver(SupportDeriver&&) noexcept;
    SupportDeriver& operator=(SupportDeriver&&) noexcept;
    SupportDeriver(const SupportDeriver&) = delete;
    SupportDeriver& operator=(const SupportDeriver&) = delete;

    const AuthorityBinding& binding() const noexcept;
    DerivedSupport derive(
        std::uint32_t rate,
        std::uint32_t probe_samples,
        std::int64_t integer_epoch,
        double fractional_offset);
    CacheStats cache_stats() const noexcept;
    void clear_cache() noexcept;

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};

// Borrowed adapter for the neutral runtime port. The deriver must remain at a
// stable address and outlive every port call; do not move it while borrowed.
SupportDerivationPort derivation_port(SupportDeriver&) noexcept;

}  // namespace leo::adaptive::server_compat
