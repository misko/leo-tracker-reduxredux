#include "timebase.hpp"
#include <cmath>
#include <stdexcept>

namespace leo::adaptive::timing {
Status read_bracket(const ReadPort& p, Bracket& out) {
    if (!p.monotonic_ns || !p.utc_ns || !p.counter) return Status::read_error;
    if (!p.exact_counter) return Status::unqualified_counter;
    Bracket b;
    b.exact_counter = true;
    if (p.monotonic_ns(p.context, &b.monotonic_before_ns) ||
        p.utc_ns(p.context, &b.utc_before_ns) ||
        p.counter(p.context, &b.counter) ||
        p.utc_ns(p.context, &b.utc_after_ns) ||
        p.monotonic_ns(p.context, &b.monotonic_after_ns)) return Status::read_error;
    out = b;
    return Status::ok;
}
Timebase::Timebase(Config c) : config_(c) {
    if (!c.sample_rate_hz || !c.maximum_bracket_ns || !c.maximum_age_ns ||
        c.maximum_bracket_ns > c.maximum_age_ns || !c.retained_anchors ||
        c.retained_anchors > 1024 || !std::isfinite(c.rate_tolerance_ppm) ||
        c.rate_tolerance_ppm < 0 || c.rate_tolerance_ppm > 1000000)
        throw std::invalid_argument("invalid counter/UTC timing configuration");
}
Status Timebase::begin(std::uint64_t generation) {
    if (!generation || generation <= generation_) return Status::invalid_generation;
    generation_ = generation;
    anchors_.clear();
    qualified_ = true;
    return Status::ok;
}
Status Timebase::invalidate(Status reason) {
    qualified_ = false;
    anchors_.clear();
    return reason;
}
Status Timebase::observe(const Bracket& b) {
    if (!generation_ || !qualified_) return Status::unavailable;
    if (!b.exact_counter) return Status::unqualified_counter;
    if (b.utc_before_ns <= 0 || b.utc_after_ns <= 0 ||
        b.monotonic_after_ns < b.monotonic_before_ns)
        return invalidate(Status::invalid_bracket);
    if (b.utc_after_ns < b.utc_before_ns)
        return invalidate(Status::clock_discontinuity);
    const auto width = static_cast<std::uint64_t>(b.utc_after_ns - b.utc_before_ns);
    const auto mono_width = b.monotonic_after_ns - b.monotonic_before_ns;
    if (static_cast<long double>(width) > static_cast<long double>(mono_width) +
            config_.clock_resolution_ns)
        return invalidate(Status::clock_discontinuity);
    if (mono_width > config_.maximum_bracket_ns || width > config_.maximum_bracket_ns)
        return invalidate(Status::invalid_bracket);
    Anchor a{generation_, b.counter, b.monotonic_before_ns + mono_width / 2,
        b.utc_before_ns + static_cast<std::int64_t>(width / 2),
        config_.sample_rate_hz, mono_width};
    if (!anchors_.empty()) {
        const auto& old = anchors_.back();
        if (a.counter < old.counter) return invalidate(Status::counter_regression);
        if (a.monotonic_ns < old.monotonic_ns || a.utc_ns < old.utc_ns)
            return invalidate(Status::clock_discontinuity);
        // Subtract integers before conversion, preserving >2^53 counter epochs.
        const long double elapsed = static_cast<long double>(a.counter - old.counter) *
            1e9L / config_.sample_rate_hz;
        const long double utc_elapsed = a.utc_ns - old.utc_ns;
        const long double mono_elapsed = a.monotonic_ns - old.monotonic_ns;
        const long double bracket_error = (static_cast<long double>(a.bracket_width_ns) +
            old.bracket_width_ns) / 2 + config_.clock_resolution_ns;
        const long double drift_error = elapsed * config_.rate_tolerance_ppm / 1e6L;
        if (std::fabs(utc_elapsed - elapsed) > bracket_error + drift_error ||
            std::fabs(utc_elapsed - mono_elapsed) > 2 * bracket_error)
            return invalidate(Status::clock_discontinuity);
    }
    anchors_.push_back(a);
    if (anchors_.size() > config_.retained_anchors) anchors_.pop_front();
    return Status::ok;
}
Status Timebase::anchor_for(std::uint64_t generation, std::uint64_t counter,
                           Anchor& out, double& uncertainty,
                           std::uint64_t support_samples) const {
    if (generation != generation_) return Status::invalid_generation;
    if (!qualified()) return Status::unavailable;
    for (auto i = anchors_.rbegin(); i != anchors_.rend(); ++i) {
        if (counter < i->counter) continue;
        const long double elapsed = (static_cast<long double>(counter - i->counter) + support_samples) *
            1e9L / config_.sample_rate_hz;
        if (elapsed > config_.maximum_age_ns) return Status::expired;
        out = *i;
        uncertainty = static_cast<double>(i->bracket_width_ns +
            2 * elapsed * config_.rate_tolerance_ppm / 1e6L +
            2 * static_cast<long double>(config_.clock_resolution_ns));
        return Status::ok;
    }
    return Status::unavailable;
}
} // namespace leo::adaptive::timing
