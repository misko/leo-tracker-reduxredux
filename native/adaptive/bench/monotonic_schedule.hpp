#pragma once
#include <chrono>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <time.h>

namespace leo::adaptive::bench {
// Linux-local scheduling authority; never capture UTC or a persisted timestamp.
// A controller and its child processes can share this clock without depending
// on the implementation-defined epoch of std::chrono::steady_clock.
struct MonotonicClock {
    using rep = int64_t;
    using period = std::nano;
    using duration = std::chrono::nanoseconds;
    using time_point = std::chrono::time_point<MonotonicClock>;
    static constexpr bool is_steady = true;
    static time_point now() {
        timespec value{};
        if (clock_gettime(CLOCK_MONOTONIC, &value))
            throw std::runtime_error("monotonic clock failed");
        return time_point(std::chrono::seconds(value.tv_sec) + duration(value.tv_nsec));
    }
};

inline MonotonicClock::time_point scheduled_origin(uint64_t requested_ns,
                                                  MonotonicClock::time_point now) {
    if (!requested_ns || requested_ns > static_cast<uint64_t>(std::numeric_limits<int64_t>::max()))
        throw std::runtime_error("invalid monotonic origin");
    const MonotonicClock::time_point origin{MonotonicClock::duration(requested_ns)};
    if (origin <= now) throw std::runtime_error("missed monotonic origin");
    if (origin - now > std::chrono::seconds(60))
        throw std::runtime_error("monotonic origin exceeds initialization lead limit");
    return origin;
}
}
