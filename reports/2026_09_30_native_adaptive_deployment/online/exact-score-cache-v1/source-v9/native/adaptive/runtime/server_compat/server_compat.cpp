#include "server_compat.hpp"

#include "pow3.h"
#include "python_float_repr.hpp"

#include <algorithm>
#include <cfenv>
#include <clocale>
#include <cmath>
#include <cstring>
#include <stdexcept>
#include <utility>

namespace leo::adaptive::server_compat {
namespace {

double nearest_even(double value) {
    const double lower = std::floor(value);
    const double fraction = value - lower;
    return fraction < 0.5 ? lower
        : fraction > 0.5 ? lower + 1.0
        : std::fmod(lower, 2.0) == 0.0 ? lower : lower + 1.0;
}

double binary64(double value) {
    volatile double rounded = value;
    return rounded;
}

double expansion_sum(const double* values, std::size_t count) {
    double partials[1024];
    std::size_t size = 0;
    for (std::size_t item = 0; item < count; ++item) {
        double next = values[item];
        std::size_t output = 0;
        for (std::size_t index = 0; index < size; ++index) {
            double partial = partials[index];
            if (std::abs(next) < std::abs(partial)) std::swap(next, partial);
            const double high = binary64(next + partial);
            const double low = binary64(partial - binary64(high - next));
            if (low != 0.0) partials[output++] = low;
            next = high;
        }
        partials[output] = next;
        size = output + 1;
    }
    double high = 0.0;
    double low = 0.0;
    if (size != 0) {
        high = partials[--size];
        while (size != 0) {
            const double next = high;
            const double partial = partials[--size];
            high = binary64(next + partial);
            low = binary64(partial - binary64(high - next));
            if (low != 0.0) break;
        }
        if (size != 0 && ((low < 0.0 && partials[size - 1] < 0.0) ||
            (low > 0.0 && partials[size - 1] > 0.0))) {
            const double doubled = binary64(low * 2.0);
            const double corrected = binary64(high + doubled);
            if (doubled == binary64(corrected - high)) high = corrected;
        }
    }
    return high;
}

void require_environment() {
    if (std::fegetround() != FE_TONEAREST) {
        throw std::invalid_argument("server compatibility requires round-to-nearest");
    }
    const lconv* numeric = std::localeconv();
    if (numeric == nullptr || numeric->decimal_point == nullptr ||
        numeric->thousands_sep == nullptr || numeric->grouping == nullptr ||
        std::strcmp(numeric->decimal_point, ".") != 0 ||
        numeric->thousands_sep[0] != '\0' || numeric->grouping[0] != '\0') {
        throw std::invalid_argument("server compatibility requires C numeric conventions");
    }
}

Support derive_uncached(
    std::uint32_t rate,
    std::uint32_t samples,
    std::int64_t epoch,
    double fractional_offset) {
    if (rate == 0 || rate > 10'000'000 || samples == 0 || samples > rate / 50 ||
        epoch < 0 || epoch >= static_cast<std::int64_t>(samples) ||
        !std::isfinite(fractional_offset) || std::abs(fractional_offset) > 2.0) {
        throw std::invalid_argument("invalid server compatibility support input");
    }
    const bool integer =
        std::abs(fractional_offset - nearest_even(fractional_offset)) <= 1.0e-12;
    const int left = integer ? 0 : 7;
    const int right = integer ? 0 : 8;
    const double period = static_cast<double>(rate) / 750.0;
    const double symbol = rate * 4.4e-6;
    const std::int64_t template_samples = static_cast<std::int64_t>(nearest_even(period));
    double centers[1024];
    std::size_t count = 0;
    std::int64_t start = samples;
    std::int64_t end = 0;
    for (unsigned frame = 0; frame < 16; ++frame) {
        const std::int64_t base = epoch +
            static_cast<std::int64_t>(nearest_even(frame * period));
        if (base + fractional_offset >= samples ||
            base + nearest_even(2.0 * symbol) + fractional_offset >= samples) break;
        for (int ordinal = 2; ordinal < 66; ++ordinal) {
            const std::int64_t first =
                static_cast<std::int64_t>(nearest_even(ordinal * symbol));
            const std::int64_t after = std::min<std::int64_t>(
                static_cast<std::int64_t>(nearest_even((ordinal + 1) * symbol)),
                template_samples);
            const std::int64_t width = after - first;
            const double point = base + first + fractional_offset;
            if (width < 2 || point < left || point + width - 1 >= samples - right) continue;
            centers[count++] = binary64(point + static_cast<double>(width - 1) / 2.0);
            start = std::min(start, static_cast<std::int64_t>(std::floor(point)) - left);
            end = std::max(
                end, static_cast<std::int64_t>(std::floor(point + width - 1)) + right + 1);
        }
    }
    if (count < 2) throw std::invalid_argument("insufficient server compatibility support");
    const double center = binary64(expansion_sum(centers, count) / count);
    double second[1024];
    double third[1024];
    for (std::size_t index = 0; index < count; ++index) {
        const double deviation = binary64(binary64(centers[index] - center) / rate);
        second[index] = binary64(deviation * deviation);
        third[index] = leo_server_pow3_fma(deviation);
    }
    const double moment2 =
        binary64(binary64(expansion_sum(second, count) / count) / 2.0);
    const double moment3 =
        binary64(binary64(expansion_sum(third, count) / count) / 6.0);
    return {start, end, center, moment2, moment3, static_cast<std::uint32_t>(count)};
}

DerivedSupport complete(Support support) {
    return {
        support,
        {"1.0", "0.0", detail::python_float_repr(support.moment2),
            detail::python_float_repr(support.moment3)},
        false,
    };
}

}  // namespace

AuthorityBinding authority_binding() {
    return {kProfileName, kProfileManifestDigest};
}

struct SupportDeriver::Impl {
    explicit Impl(AuthorityBinding value) : binding(std::move(value)) {}
    AuthorityBinding binding;
    std::uint32_t rate{};
    std::uint32_t samples{};
    std::int64_t epoch{};
    std::uint64_t fraction_bits{};
    int rounding{};
    DerivedSupport result;
    CacheStats statistics;
};

SupportDeriver::SupportDeriver(AuthorityBinding binding)
    : impl_(std::make_unique<Impl>(std::move(binding))) {
    if (impl_->binding.profile_name != kProfileName ||
        impl_->binding.profile_manifest_digest != kProfileManifestDigest) {
        throw std::invalid_argument("server compatibility authority binding mismatch");
    }
    require_environment();
}

SupportDeriver::~SupportDeriver() = default;
SupportDeriver::SupportDeriver(SupportDeriver&&) noexcept = default;
SupportDeriver& SupportDeriver::operator=(SupportDeriver&&) noexcept = default;

const AuthorityBinding& SupportDeriver::binding() const noexcept {
    return impl_->binding;
}

DerivedSupport SupportDeriver::derive(
    std::uint32_t rate,
    std::uint32_t samples,
    std::int64_t epoch,
    double fractional_offset) {
    require_environment();
    std::uint64_t fraction_bits = 0;
    static_assert(sizeof(fraction_bits) == sizeof(fractional_offset), "binary64 required");
    std::memcpy(&fraction_bits, &fractional_offset, sizeof(fraction_bits));
    const int rounding = std::fegetround();
    if (impl_->statistics.populated && impl_->rate == rate && impl_->samples == samples &&
        impl_->epoch == epoch && impl_->fraction_bits == fraction_bits &&
        impl_->rounding == rounding) {
        ++impl_->statistics.hits;
        DerivedSupport output = impl_->result;
        output.cache_hit = true;
        return output;
    }
    ++impl_->statistics.misses;
    DerivedSupport output = complete(
        derive_uncached(rate, samples, epoch, fractional_offset));
    impl_->rate = rate;
    impl_->samples = samples;
    impl_->epoch = epoch;
    impl_->fraction_bits = fraction_bits;
    impl_->rounding = rounding;
    impl_->result = output;
    impl_->statistics.populated = true;
    return output;
}

CacheStats SupportDeriver::cache_stats() const noexcept {
    return impl_->statistics;
}

void SupportDeriver::clear_cache() noexcept {
    impl_->statistics.populated = false;
}

namespace {
SupportDerivationStatus derive_through_port(
    void* context,
    std::uint32_t rate,
    std::uint32_t samples,
    std::int64_t epoch,
    double fractional_offset,
    SupportDerivation* output) {
    if(!context || !output) return SupportDerivationStatus::invalid_input;
    try {
        const auto derived=static_cast<SupportDeriver*>(context)->derive(
            rate,samples,epoch,fractional_offset);
        output->numeric=derived.numeric;
        output->factorial_moment_lexemes=derived.factorial_moment_lexemes;
        return SupportDerivationStatus::ok;
    } catch(const std::invalid_argument&) {
        return SupportDerivationStatus::invalid_input;
    } catch(...) {
        return SupportDerivationStatus::unavailable;
    }
}
}

SupportDerivationPort derivation_port(SupportDeriver& deriver) noexcept {
    const auto& binding=deriver.binding();
    return {&deriver,binding.profile_name,binding.profile_manifest_digest,
        derive_through_port};
}

}  // namespace leo::adaptive::server_compat
