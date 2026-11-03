#ifndef LEO_ADAPTIVE_SCANNER_TIMING_H
#define LEO_ADAPTIVE_SCANNER_TIMING_H

#include <cerrno>
#include <cstdint>
#include <limits>

/* Match the maintained scan-session transition contract. A recall completing
 * inside the nominal selection-to-valid budget consumes that budget. A recall
 * completing later receives a full settling interval after its measured end.
 * A same-profile visit performs no recall and needs no transition interval. */
inline int leo_scanner_valid_start(std::uint64_t selection_counter,
    std::uint64_t recall_counter_after, std::uint64_t transition_ticks,
    bool recalled, std::uint64_t& valid_start)
{
    if (!recalled) {
        valid_start = selection_counter;
        return 0;
    }
    if (selection_counter > std::numeric_limits<std::uint64_t>::max() -
            transition_ticks)
        return -EOVERFLOW;
    const std::uint64_t nominal = selection_counter + transition_ticks;
    if (recall_counter_after <= nominal) {
        valid_start = nominal;
        return 0;
    }
    if (recall_counter_after > std::numeric_limits<std::uint64_t>::max() -
            transition_ticks)
        return -EOVERFLOW;
    valid_start = recall_counter_after + transition_ticks;
    return 0;
}

#endif
