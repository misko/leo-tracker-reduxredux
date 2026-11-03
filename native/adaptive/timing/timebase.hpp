#pragma once
#include <cstddef>
#include <cstdint>
#include <deque>

namespace leo::adaptive::timing {
enum class Status {
    ok, invalid_config, invalid_generation, invalid_bracket, unqualified_counter,
    read_error, counter_regression, clock_discontinuity, unavailable, expired
};
struct Config {
    std::uint32_t sample_rate_hz{};
    std::uint64_t maximum_bracket_ns{};
    std::uint64_t maximum_age_ns{};
    double rate_tolerance_ppm{};
    std::uint64_t clock_resolution_ns{};
    std::size_t retained_anchors{8};
};
struct Bracket {
    std::uint64_t monotonic_before_ns{}, monotonic_after_ns{}, counter{};
    std::int64_t utc_before_ns{}, utc_after_ns{};
    bool exact_counter{};
};
// Value-owned calibration. It may be retained with a visit after later refreshes.
struct Anchor {
    std::uint64_t generation{}, counter{}, monotonic_ns{};
    std::int64_t utc_ns{};
    std::uint32_t sample_rate_hz{};
    std::uint64_t bracket_width_ns{};
};
struct ReadPort {
    void* context{};
    int (*monotonic_ns)(void*, std::uint64_t*){};
    int (*utc_ns)(void*, std::int64_t*){};
    int (*counter)(void*, std::uint64_t*){};
    bool exact_counter{};
};
// Clocks bracket the counter call, including its complete latency. Host arrival
// timestamps and software delivery ordinals must not claim exact_counter.
Status read_bracket(const ReadPort&, Bracket&);

// Single-owner state. Clock steps/resets invalidate all timing until an explicit
// newer generation begins; a refresh never silently manufactures continuity.
class Timebase {
public:
    explicit Timebase(Config);
    Status begin(std::uint64_t generation);
    Status observe(const Bracket&);
    Status anchor_for(std::uint64_t generation, std::uint64_t counter,
                      Anchor&, double& uncertainty_width_ns,
                      std::uint64_t support_samples = 0) const;
    bool qualified() const { return qualified_ && !anchors_.empty(); }
    std::size_t retained() const { return anchors_.size(); }
private:
    Status invalidate(Status);
    Config config_;
    std::uint64_t generation_{};
    bool qualified_{};
    std::deque<Anchor> anchors_;
};
} // namespace leo::adaptive::timing
