#pragma once
#include "tracking.hpp"

namespace leo::adaptive::pipeline {
struct SelectionAudit {
    std::size_t input_tracks=0, output_tracks=0;
    std::size_t reused_memberships_removed=0, insufficient_memberships_removed=0;
};
// Optional positioning policy, not a change to tracker output. Assign each
// candidate to at most one retained fragment. No orbit/position/reference input.
tracking::Result select_exclusive_candidates(const tracking::Result& hypotheses,
    const std::vector<tracking::Candidate>& observations, SelectionAudit& audit);
}
